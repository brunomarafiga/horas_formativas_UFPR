from pyscript import document, window
import js
import json
import asyncio
from datetime import datetime
import base64

# --- Estado da Aplicação ---
config = {
    'apiKey': '',
    'dataIngresso': ''
}

certificados = []
hashes_processados = set()

# DOM Elements
btnConfig = document.getElementById('btn-config')
modalConfig = document.getElementById('config-modal')
btnSaveConfig = document.getElementById('btn-save-config')
inputApiKey = document.getElementById('input-apikey')
inputMes = document.getElementById('input-mes')
inputAno = document.getElementById('input-ano')

# Preencher anos dinamicamente (2015 até o ano atual + 1)
from datetime import date
for y in range(2015, date.today().year + 2):
    opt = document.createElement('option')
    opt.value = str(y)
    opt.textContent = str(y)
    inputAno.appendChild(opt)

dropzone = document.getElementById('dropzone')
fileInput = document.getElementById('file-input')
statusPanel = document.getElementById('processing-status')
currentFileName = document.getElementById('current-file-name')
btnClear = document.getElementById('btn-clear')
tableBody = document.getElementById('cert-table-body')

elTotalHours = document.getElementById('total-hours')
elG1Hours = document.getElementById('grupo1-hours')
elG2Hours = document.getElementById('grupo2-hours')
progG1 = document.getElementById('prog-g1')
progG2 = document.getElementById('prog-g2')

# --- Limites por Categoria UFPR ---
LIMITES_CATEGORIA = {
    # Grupo 1
    'Disciplinas eletivas': 60,
    'Monitoria': 60,
    'Pesquisa ou iniciacao cientifica': 60,
    'Estagio nao obrigatorio': 60,
    'Apresentacao de trabalhos': 60,
    'Extensao vinculada a UFPR': 30,
    'Participacao em eventos': 30,
    'Visitas tecnicas': 30,
    'Palestras tecnicas': 20,
    'Curso de extensao afim': 20,
    'Representacao academica': 20,
    'Projeto integrado': 20,
    'Curso superior completo': 80,
    'Outras atividades': 30,
    # Grupo 2
    'Curso de idiomas': 60,
    'Comissao de eventos': 40,
    'Empresa Junior': 30,
    'Voluntariado': 30,
    'Atividades culturais': 20,
    'Atividades desportivas': 20,
    'Curso de extensao geral': 20,
    'Programas e projetos institucionais': 20,
    'Desafios ou competicoes': 20,
}

def get_limite_categoria(cat_name):
    """Busca o limite de horas da categoria, fazendo match flexivel."""
    cat_lower = cat_name.lower().replace('ã','a').replace('é','e').replace('í','i').replace('ó','o').replace('ú','u').replace('ç','c')
    for key, limit in LIMITES_CATEGORIA.items():
        if key.lower() in cat_lower or cat_lower in key.lower():
            return limit
    return 30  # default seguro

# --- Funções de UI e Tabela ---

def is_date_valid(cert_date):
    if not config['dataIngresso'] or not cert_date:
        return False
    try:
        # Input type="month" retorna YYYY-MM
        dt_ingresso = datetime.strptime(config['dataIngresso'], "%Y-%m")
        # Certificado vem como YYYY-MM-DD
        dt_cert = datetime.strptime(cert_date[:7], "%Y-%m")
        return dt_cert >= dt_ingresso
    except Exception:
        return False

def render_table():
    # Atualiza a validade de todos (caso a data de ingresso tenha mudado)
    for c in certificados:
        if c.get('data'):
            c['valido'] = is_date_valid(c['data'])

    tableBody.innerHTML = ''

    if len(certificados) == 0:
        tableBody.innerHTML = '<tr class="empty-row"><td colspan="7">Nenhum certificado processado ainda. Adicione PDFs acima!</td></tr>'
        elTotalHours.innerHTML = '0h <span class="limit">/ 140h min</span>'
        elG1Hours.innerHTML = '0h <span class="limit">(Mín: 40h | Máx: 70h)</span>'
        elG2Hours.innerHTML = '0h <span class="limit">(Mín: 40h | Máx: 70h)</span>'
        progG1.style.width = '0%'
        progG2.style.width = '0%'
        return

    g1_total = 0
    g2_total = 0

    for cert in certificados:
        row = document.createElement('tr')
        
        status_badge = '<span class="badge success"><i class="fa-solid fa-check"></i> Válido</span>'
        if cert.get('status') != 'Sucesso':
            status_badge = '<span class="badge danger"><i class="fa-solid fa-times"></i> Erro</span>'
        elif not cert.get('valido'):
            status_badge = f'<span class="badge warning" title="Anterior a {config["dataIngresso"]}"><i class="fa-solid fa-calendar-xmark"></i> Inválido (Data)</span>'

        # Soma as horas sse válido e sucesso
        if cert.get('status') == 'Sucesso' and cert.get('valido'):
            grupo = cert.get('grupo', '')
            if '1' in grupo:
                g1_total += cert.get('horas', 0)
            elif '2' in grupo:
                g2_total += cert.get('horas', 0)

        # Montar a linha
        data_str = cert.get('data', '--')
        nome = cert.get('fileName', '')
        assunto = cert.get('assunto', '')
        grupo_str = cert.get('grupo', '')
        cat = cert.get('categoria_ufpr', 'Indefinido')
        horas = cert.get('horas', 0)
        cid = cert.get('id', '')

        # Calcular horas validadas (com teto por categoria)
        limite_cat = get_limite_categoria(cat)
        horas_validadas = min(horas, limite_cat) if (cert.get('status') == 'Sucesso' and cert.get('valido')) else 0

        row.innerHTML = f"""
            <td>{status_badge}</td>
            <td>{data_str}</td>
            <td><strong>{nome}</strong><br><small style="color:var(--gray)">{assunto}</small></td>
            <td>{grupo_str} - {cat}<br><small style="color:var(--gray)">Limite: {limite_cat}h</small></td>
            <td><strong>{horas}h</strong></td>
            <td><strong>{horas_validadas}h</strong></td>
            <td>
                 <button class="btn-small btn-remove" data-id="{cid}">Remover</button>
            </td>
        """
        tableBody.appendChild(row)

    # Attach remove event listeners using event delegation equivalent
    btns_remove = document.querySelectorAll('.btn-remove')
    for b in btns_remove:
        b.onclick = handle_remove_cert

    # Final cálculos (Tetos de 70h)
    g1_valido = min(g1_total, 70)
    g2_valido = min(g2_total, 70)
    total_geral = g1_valido + g2_valido

    # Atualiza Dashboards
    elTotalHours.innerHTML = f'{total_geral}h <span class="limit">/ 140h min</span>'
    if total_geral >= 140:
        elTotalHours.style.color = 'var(--success)'
    else:
        elTotalHours.style.color = ''

    elG1Hours.innerHTML = f'{g1_total}h computadas <span class="limit">(Aproveitado: {g1_valido}h)</span>'
    elG2Hours.innerHTML = f'{g2_total}h computadas <span class="limit">(Aproveitado: {g2_valido}h)</span>'
    
    # Progress bars
    g1_pct = min((g1_valido / 70) * 100, 100)
    g2_pct = min((g2_valido / 70) * 100, 100)
    progG1.style.width = f"{g1_pct}%"
    progG2.style.width = f"{g2_pct}%"


def load_config():
    saved = js.localStorage.getItem('ufpr_config')
    if saved:
        try:
            cfg = json.loads(saved)
            config['apiKey'] = cfg.get('apiKey', '')
            config['dataIngresso'] = cfg.get('dataIngresso', '')
            inputApiKey.value = config['apiKey']
            # Restaurar selects de mês/ano
            if config['dataIngresso'] and '-' in config['dataIngresso']:
                parts = config['dataIngresso'].split('-')
                inputAno.value = parts[0]
                inputMes.value = parts[1]
        except Exception as e:
            js.console.error("Erro lendo config localStorage", str(e))

def load_dashboard():
    global certificados
    saved = js.localStorage.getItem('ufpr_certs')
    if saved:
        try:
            certificados = json.loads(saved)
            for c in certificados:
                hashes_processados.add(c.get('id'))
            render_table()
        except Exception as e:
            js.console.error("Erro lendo certs localStorage", str(e))

def save_dashboard():
    js.localStorage.setItem('ufpr_certs', json.dumps(certificados))
    render_table()

def handle_remove_cert(e):
    global certificados
    btn = e.currentTarget
    cid = btn.getAttribute('data-id')
    
    certificados = [c for c in certificados if c.get('id') != cid]
    if cid in hashes_processados:
        hashes_processados.remove(cid)
        
    save_dashboard()


# --- Eventos Mapeados ---

def on_config_open(e):
    modalConfig.showModal()
btnConfig.onclick = on_config_open

def on_config_save(e):
    k = inputApiKey.value.strip()
    mes = inputMes.value
    ano = inputAno.value
    
    if not k or not mes or not ano:
        js.alert("Por favor, preencha todos os campos!")
        return
    
    d = f"{ano}-{mes}"
    config['apiKey'] = k
    config['dataIngresso'] = d
    
    js.localStorage.setItem('ufpr_config', json.dumps(config))
    modalConfig.close()
    
    if len(certificados) > 0:
        render_table()
        
btnSaveConfig.onclick = on_config_save

def on_clear(e):
    global certificados
    if js.confirm("Tem certeza que deseja apagar todo o histórico lido?"):
        certificados = []
        hashes_processados.clear()
        save_dashboard()
btnClear.onclick = on_clear

# --- Exportar CSV ---
btnExportCsv = document.getElementById('btn-export-csv')

def on_export_csv(e):
    if len(certificados) == 0:
        js.alert("Nenhum certificado para exportar!")
        return
    
    # Filtrar apenas os com sucesso e ordenar por data crescente
    validos = [c for c in certificados if c.get('status') == 'Sucesso']
    validos.sort(key=lambda c: c.get('data', '0000-00-00'))
    
    # Montar CSV
    linhas = ["Certificado,Data,Categoria,Grupo,Horas,Valido"]
    for c in validos:
        nome = c.get('assunto', '').replace(',', ' -')
        data = c.get('data', '')
        cat = c.get('categoria_ufpr', '').replace(',', ' -')
        grupo = c.get('grupo', '')
        horas = str(c.get('horas', 0))
        valido = "Sim" if c.get('valido') else "Nao"
        linhas.append(f"{nome},{data},{cat},{grupo},{horas},{valido}")
    
    csv_content = "\n".join(linhas)
    
    # Gerar download via Blob JS
    from pyodide.ffi import to_js
    blob = js.Blob.new(
        to_js([csv_content]),
        to_js({"type": "text/csv;charset=utf-8;"}, dict_converter=js.Object.fromEntries)
    )
    url = js.URL.createObjectURL(blob)
    
    link = document.createElement('a')
    link.setAttribute('href', url)
    link.setAttribute('download', 'certificados_ufpr.csv')
    link.style.display = 'none'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    js.URL.revokeObjectURL(url)

btnExportCsv.onclick = on_export_csv

# --- Drag & Drop ---
def prevent_defaults(e):
    e.preventDefault()
    e.stopPropagation()

def on_drag_enter(e):
    prevent_defaults(e)
    dropzone.classList.add('dragover')

def on_drag_leave(e):
    prevent_defaults(e)
    dropzone.classList.remove('dragover')

dropzone.onclick = lambda e: fileInput.click()
dropzone.ondragenter = on_drag_enter
dropzone.ondragover = on_drag_enter
dropzone.ondragleave = on_drag_leave

def handle_drop(e):
    prevent_defaults(e)
    dropzone.classList.remove('dragover')
    dt = e.dataTransfer
    files = dt.files
    # files is a JS FileList, start async task
    asyncio.create_task(process_multiple_files(files))
    
dropzone.ondrop = handle_drop

def handle_file_select(e):
    files = e.target.files
    asyncio.create_task(process_multiple_files(files))

fileInput.onchange = handle_file_select


# --- Lógica Core (Upload e Gemini) ---

# Cache do modelo descoberto para não consultar a API a cada arquivo
_cached_model = None

async def discover_best_model():
    """Consulta a API do Google para encontrar o melhor modelo disponível.
    Prioridade: modelos 'pro' estáveis > flash estáveis > qualquer outro.
    Faz fallback para 'gemini-2.0-flash' que é o estável garantido."""
    global _cached_model
    if _cached_model:
        return _cached_model
    
    try:
        list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={config['apiKey']}"
        resp = await js.fetch(list_url)
        if not resp.ok:
            _cached_model = "gemini-2.0-flash"
            return _cached_model
        
        data = await resp.json()
        models_list = data.to_py().get('models', [])
        
        # Filtra modelos que suportam generateContent
        generative = []
        for m in models_list:
            name = m.get('name', '')
            methods = m.get('supportedGenerationMethods', [])
            if 'generateContent' in methods and 'gemini' in name:
                # Pega só o nome curto (ex: "models/gemini-2.0-flash" -> "gemini-2.0-flash")
                short = name.replace('models/', '')
                generative.append(short)
        
        # Prioridade: pro > flash, versão mais recente > antiga
        def model_score(name):
            score = 0
            if 'experimental' in name:
                score -= 5  # penaliza apenas experimental (muito instável)
            if 'pro' in name:
                score += 5
            if 'flash' in name:
                score += 3
            if 'preview' in name:
                score += 1  # preview é aceitável, leve bônus por ser mais novo
            # Modelos mais recentes (número maior = melhor)
            import re
            nums = re.findall(r'(\d+\.\d+)', name)
            if nums:
                score += float(nums[0]) * 2
            return score
        
        generative.sort(key=model_score, reverse=True)
        
        if generative:
            _cached_model = generative[0]
            js.console.log(f"Modelo Gemini selecionado automaticamente: {_cached_model}")
        else:
            _cached_model = "gemini-2.0-flash"
            
    except Exception as e:
        js.console.error("Falha ao descobrir modelos, usando fallback", str(e))
        _cached_model = "gemini-2.0-flash"
    
    return _cached_model

async def analyze_with_gemini(b64_string, filename):
    model_name = await discover_best_model()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={config['apiKey']}"
    
    prompt_text = """
        Analise este certificado acadêmico/universitário e extraia rigorosamente as informações no formato JSON abaixo.
        Atenção às regras de Grupos Formativos da UFPR.
        
        Grupo 1 (Acadêmico): Disciplinas eletivas, Monitoria, Pesquisa/Iniciação, Estágio, Trabalhos em Eventos, Extensão vinculada à UFPR, Participação em eventos, Visitas técnicas, Palestras técnicas, Curso de extensão afim, Representação acadêmica, Projeto integrado.
        Grupo 2 (Social): Curso de Idiomas, Comissão de eventos, Empresa Júnior, Voluntariado, Atividades culturais (coral/esporte), Curso de extensão geral, Desafios/Competições.
        
        REGRAS IMPORTANTES PARA HORAS:
        - Se o certificado mencionar explicitamente a carga horária, use esse valor.
        - Se o certificado for de uma plataforma como Coursera, Alura, DIO, Udemy ou similar e não mencionar horas, ESTIME a carga horária com base na duração típica do curso (ex: cursos do Google no Coursera geralmente têm entre 15 e 25 horas).
        - Se for um evento (palestra, seminário, workshop), estime pela duração do evento.
        - NUNCA retorne 0 horas a menos que seja realmente impossível estimar.
        
        Retorne um JSON puro, sem crases markdown, exatamente com estas chaves:
        {
            "data": "Apenas a data de conclusão ou emissão no formato YYYY-MM-DD",
            "assunto": "Título curto do certificado/evento",
            "grupo": "Apenas o texto 'Grupo 1' ou 'Grupo 2' ou 'Outro'",
            "categoria_ufpr": "O nome da categoria específica que ele se encaixa dentre os listados acima (Ex: Participação em eventos)",
            "horas": <numero_inteiro_de_horas_estime_se_necessario>
        }
    """
    
    payload = {
        "contents": [{
            "parts": [
                { "text": prompt_text },
                {
                    "inline_data": {
                        "mime_type": "application/pdf",
                        "data": b64_string
                    }
                }
            ]
        }],
        "generationConfig": {
            "temperature": 0.1
        }
    }
    
    from pyodide.ffi import to_js
    
    # Converter o dict Python para JS Object de uma vez (evita JsProxy item assignment)
    fetch_options = to_js({
        "method": "POST",
        "headers": {
            "Content-Type": "application/json"
        },
        "body": json.dumps(payload)
    }, dict_converter=js.Object.fromEntries)
    
    response = await js.fetch(url, fetch_options)
    
    if not response.ok:
        err_msg = await response.text()
        raise Exception(f"HTTP error {response.status}: {err_msg}")
        
    data = await response.json()
    # Conversão do JS Object (PyProxy) pro dict Python usando to_py()
    py_data = data.to_py()
    
    try:
        raw_target = py_data['candidates'][0]['content']['parts'][0]['text']
        return raw_target
    except Exception as e:
        js.console.error("Erro dissecando resposta JSON do Gemini", str(e), str(py_data))
        raise Exception("Resposta vazia da API")


async def process_multiple_files(files):
    if not config['apiKey']:
        js.alert("Configure a API Key do Gemini primeiro!")
        modalConfig.showModal()
        return

    # Count actual PDFs
    pdf_files = []
    for i in range(files.length):
        f = files.item(i)
        if f.type == 'application/pdf':
            pdf_files.append(f)
            
    if len(pdf_files) == 0:
        return
        
    statusPanel.classList.remove('hidden')
    dropzone.style.display = 'none'

    for index, file in enumerate(pdf_files):
        filename = file.name
        file_size = file.size
        
        file_id = f"{filename}_{file_size}"
        
        if file_id in hashes_processados:
            js.console.log("Arquivo já processado", filename)
            continue
            
        currentFileName.textContent = f"({index+1}/{len(pdf_files)}) {filename}"
        
        try:
            # JS Promise for ArrayBuffer
            array_buf = await file.arrayBuffer()
            # Convert to py_bytearray
            u8array = js.Uint8Array.new(array_buf)
            py_bytes = bytes(u8array)
            # Encode Base64
            b64_str = base64.b64encode(py_bytes).decode('utf-8')
            
            gemini_txt = await analyze_with_gemini(b64_str, filename)
            
            # Limpar formatação JSON markdown ('```json' e '```') caso a IA fuja das regras
            clean_txt = gemini_txt.strip()
            if clean_txt.startswith("```json"):
                clean_txt = clean_txt[7:]
            if clean_txt.endswith("```"):
                clean_txt = clean_txt[:-3]
            clean_txt = clean_txt.strip()
            
            try:
                parsed = json.loads(clean_txt)
                final_item = {
                    'id': file_id,
                    'fileName': filename,
                    'data': parsed.get('data', ''),
                    'assunto': parsed.get('assunto', 'Falha no Assunto'),
                    'grupo': parsed.get('grupo', 'Outro'),
                    'categoria_ufpr': parsed.get('categoria_ufpr', 'Indefinido'),
                    'horas': int(parsed.get('horas', 0)),
                    'status': 'Sucesso',
                    'valido': is_date_valid(parsed.get('data', ''))
                }
            except json.JSONDecodeError:
                final_item = {
                    'id': file_id,
                    'fileName': filename,
                    'data': '2000-01-01',
                    'assunto': 'Falha na Decodificação JSON',
                    'grupo': 'Outro',
                    'categoria_ufpr': 'Falha na IA',
                    'horas': 0,
                    'status': 'Erro Formato',
                    'valido': False
                }
                
            certificados.append(final_item)
            hashes_processados.add(file_id)
            save_dashboard()

        except Exception as e:
            js.console.error(f"Erro no processamento de {filename}: {str(e)}")
            certificados.append({
                'id': file_id,
                'fileName': filename,
                'data': None,
                'assunto': str(e)[0:50] + '...',
                'grupo': 'Desconhecido',
                'categoria_ufpr': 'Desconhecido',
                'horas': 0,
                'status': 'Erro',
                'valido': False
            })
            save_dashboard()

    statusPanel.classList.add('hidden')
    dropzone.style.display = 'block'
    fileInput.value = ''

# Inicialização final
load_config()
load_dashboard()
if not config['apiKey'] or not config['dataIngresso']:
    modalConfig.showModal()
