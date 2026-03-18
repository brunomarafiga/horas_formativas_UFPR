// --- Estado da Aplicação ---
let config = {
    apiKey: '',
    dataIngresso: ''
};

// Estrutura de dados para os certificados processados
let certificados = [];
let hashes_processados = new Set(); // Para anti-duplicata simples (por nome + tamanho, ou hash verdadeiro se der tempo)

// Elementos da UI
const btnConfig = document.getElementById('btn-config');
const modalConfig = document.getElementById('config-modal');
const btnSaveConfig = document.getElementById('btn-save-config');
const inputApiKey = document.getElementById('input-apikey');
const inputData = document.getElementById('input-data');

const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('file-input');
const statusPanel = document.getElementById('processing-status');
const statusText = document.getElementById('status-text');
const currentFileName = document.getElementById('current-file-name');
const btnClear = document.getElementById('btn-clear');
const tableBody = document.getElementById('cert-table-body');

// Dashboards
const elTotalHours = document.getElementById('total-hours');
const elG1Hours = document.getElementById('grupo1-hours');
const elG2Hours = document.getElementById('grupo2-hours');
const progG1 = document.getElementById('prog-g1');
const progG2 = document.getElementById('prog-g2');

// --- Inicialização ---
document.addEventListener('DOMContentLoaded', () => {
    loadConfig();
    loadDashboard();
    
    // Se não tem chave de API, abre o modal de configuração automaticamente
    if (!config.apiKey || !config.dataIngresso) {
        modalConfig.showModal();
    }
});

// --- Configurações ---
btnConfig.addEventListener('click', () => modalConfig.showModal());

btnSaveConfig.addEventListener('click', () => {
    config.apiKey = inputApiKey.value.trim();
    config.dataIngresso = inputData.value;
    
    if(!config.apiKey || !config.dataIngresso) {
        alert("Por favor, preencha todos os campos!");
        return;
    }
    
    localStorage.setItem('ufpr_config', JSON.stringify(config));
    modalConfig.close();
    
    // Re-renderiza a tabela para recalcular validades se a data mudou
    if(certificados.length > 0) renderTable();
});

function loadConfig() {
    const saved = localStorage.getItem('ufpr_config');
    if (saved) {
        config = JSON.parse(saved);
        inputApiKey.value = config.apiKey;
        inputData.value = config.dataIngresso;
    }
}

function loadDashboard() {
    const savedCerts = localStorage.getItem('ufpr_certs');
    if (savedCerts) {
        certificados = JSON.parse(savedCerts);
        certificados.forEach(c => hashes_processados.add(c.id));
        renderTable();
    }
}

function saveDashboard() {
    localStorage.setItem('ufpr_certs', JSON.stringify(certificados));
    renderTable();
}

btnClear.addEventListener('click', () => {
    if(confirm("Tem certeza que deseja apagar todo o histórico lido? (Isso não apaga seus arquivos físicos)")) {
        certificados = [];
        hashes_processados.clear();
        saveDashboard();
    }
});

// --- Drag & Drop ---
dropzone.addEventListener('click', () => fileInput.click());

['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropzone.addEventListener(eventName, preventDefaults, false);
});

function preventDefaults (e) {
    e.preventDefault();
    e.stopPropagation();
}

['dragenter', 'dragover'].forEach(eventName => {
    dropzone.addEventListener(eventName, () => dropzone.classList.add('dragover'), false);
});

['dragleave', 'drop'].forEach(eventName => {
    dropzone.addEventListener(eventName, () => dropzone.classList.remove('dragover'), false);
});

dropzone.addEventListener('drop', (e) => {
    let dt = e.dataTransfer;
    let files = dt.files;
    handleFiles(files);
});

fileInput.addEventListener('change', function() {
    handleFiles(this.files);
});

// --- Processamento de Arquivos ---
async function handleFiles(files) {
    if (!config.apiKey) {
        alert("Configure a API Key do Gemini primeiro!");
        modalConfig.showModal();
        return;
    }

    const pdfFiles = Array.from(files).filter(f => f.type === 'application/pdf');
    if(pdfFiles.length === 0) return;

    statusPanel.classList.remove('hidden');
    dropzone.style.display = 'none';

    for (let i = 0; i < pdfFiles.length; i++) {
        let file = pdfFiles[i];
        
        // Identificador simples (nome + tamanho). Para segurança total usaríamos Hash Uint8Array.
        const fileId = file.name + '_' + file.size;
        
        if(hashes_processados.has(fileId)) {
            console.log("Arquivo já processado:", file.name);
            continue;
        }
        
        currentFileName.textContent = `(${i+1}/${pdfFiles.length}) ${file.name}`;
        
        try {
            const base64Data = await fileToBase64(file);
            const resultadoIA = await analyzeWithGemini(base64Data, file.name);
            
            if(resultadoIA) {
                const parsed = parseGeminiResponse(resultadoIA, file.name);
                parsed.id = fileId;
                
                // Validação da Data
                parsed.valido = isDateValid(parsed.data);
                
                certificados.push(parsed);
                hashes_processados.add(fileId);
                saveDashboard();
            }
        } catch (error) {
            console.error("Erro no arquivo " + file.name, error);
            certificados.push({
                id: fileId,
                fileName: file.name,
                status: 'Erro',
                data: null,
                assunto: 'Falha na leitura via IA',
                grupo: 'Desconhecido',
                horas: 0,
                valido: false
            });
            saveDashboard();
        }
    }

    statusPanel.classList.add('hidden');
    dropzone.style.display = 'block';
    
    // Limpa o input
    fileInput.value = '';
}

// Converte arquivo para base64 cortando o cabeçalho base64 padrão
function fileToBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.readAsDataURL(file);
        reader.onload = () => {
            let encoded = reader.result.toString().replace(/^data:(.*,)?/, '');
            if ((encoded.length % 4) > 0) {
                encoded += '='.repeat(4 - (encoded.length % 4));
            }
            resolve(encoded);
        };
        reader.onerror = error => reject(error);
    });
}

// --- Chamada à API REST do Gemini ---
async function analyzeWithGemini(base64str, filename) {
    // Usando o modelo gemini-3.1-pro-preview para máxima assertividade conforme preferência do usuário
    const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-pro-preview:generateContent?key=${config.apiKey}`;
    
    const promptText = `
        Analise este certificado acadêmico/universitário e extraia rigorosamente as informações no formato JSON abaixo.
        Atenção às regras de Grupos Formativos da UFPR.
        
        Grupo 1 (Acadêmico): Disciplinas eletivas, Monitoria, Pesquisa/Iniciação, Estágio, Trabalhos em Eventos, Extensão vinculada à UFPR, Participar de eventos, Visitas técnicas, Palestras técnicas, Curso de extensão afim, Representação acadêmica, Projeto integrado.
        Grupo 2 (Social): Curso de Idiomas, Comissão de eventos, Empresa Júnior, Voluntariado, Atividades culturais (coral/esporte), Curso de extensão geral, Desafios/Competições.
        
        Retorne um JSON puro, sem crases markdown, exatamente com estas chaves:
        {
            "data": "Apenas a data de conclusão ou emissão no formato YYYY-MM-DD",
            "assunto": "Título curto do certificado/evento",
            "grupo": "Apenas o texto 'Grupo 1' ou 'Grupo 2' ou 'Outro'",
            "categoria_ufpr": "O nome da categoria específica que ele se encaixa dentre os listados acima (Ex: Participação em eventos)",
            "horas": <apenas_o_numero_inteiro_de_horas_0_se_nao_tiver>
        }
    `;

    const requestBody = {
        contents: [{
            parts: [
                { text: promptText },
                {
                    inline_data: {
                        mime_type: "application/pdf",
                        data: base64str
                    }
                }
            ]
        }],
        generationConfig: {
            temperature: 0.1
        }
    };

    const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody)
    });

    if (!response.ok) {
        const err = await response.text();
        throw new Error("HTTP error " + response.status + ": " + err);
    }

    const data = await response.json();
    return data.candidates[0].content.parts[0].text;
}

function parseGeminiResponse(text, filename) {
    try {
        // Limpa possíveis blocos markdown de json
        text = text.replace(/```json/g, '').replace(/```/g, '').trim();
        const json = JSON.parse(text);
        
        return {
            fileName: filename,
            data: json.data,
            assunto: json.assunto,
            grupo: json.grupo,
            categoria_ufpr: json.categoria_ufpr,
            horas: parseInt(json.horas) || 0,
            status: 'Sucesso',
            valido: true
        };
    } catch(e) {
        console.error("Falha ao organizar JSON:", text);
        return {
            fileName: filename,
            data: "2000-01-01",
            assunto: "Falha de Interpretação JSON",
            grupo: "Outro",
            categoria_ufpr: "Indefinido",
            horas: 0,
            status: 'Erro Formato',
            valido: false
        };
    }
}

// --- Validação & UX ---
function isDateValid(certDate) {
    if(!config.dataIngresso || !certDate) return false;
    const dtIngresso = new Date(config.dataIngresso);
    const dtCert = new Date(certDate);
    // Válido apenas se o certificado é depois ou no mês do ingresso
    return dtCert >= dtIngresso; // Lógica simplificada
}

function renderTable() {
    // Reavalia validade de todos caso a data do usuário mude
    certificados.forEach(c => {
        if(c.data) c.valido = isDateValid(c.data);
    });

    tableBody.innerHTML = '';

    if (certificados.length === 0) {
        tableBody.innerHTML = '<tr class="empty-row"><td colspan="6">Nenhum certificado processado ainda. Adicione PDFs acima!</td></tr>';
        elTotalHours.innerHTML = `0h <span class="limit">/ 140h min</span>`;
        elG1Hours.innerHTML = `0h <span class="limit">(Mín: 40h | Máx: 70h)</span>`;
        elG2Hours.innerHTML = `0h <span class="limit">(Mín: 40h | Máx: 70h)</span>`;
        progG1.style.width = '0%'; progG2.style.width = '0%';
        return;
    }

    let g1Total = 0;
    let g2Total = 0;

    // TODO: Adicionar cap/limite por subcategoria (Ex: máximo de 60h para Idiomas no Grupo 2)
    // Por simplicidade na V1, capamos apenas o total por grupo em 70h

    certificados.forEach(cert => {
        const row = document.createElement('tr');
        
        let statusBadge = '<span class="badge success"><i class="fa-solid fa-check"></i> Válido</span>';
        if (cert.status !== 'Sucesso') {
            statusBadge = '<span class="badge danger"><i class="fa-solid fa-times"></i> Erro</span>';
        } else if (!cert.valido) {
            statusBadge = `<span class="badge warning" title="Anterior a ${config.dataIngresso}"><i class="fa-solid fa-calendar-xmark"></i> Inválido (Data)</span>`;
        }

        // Soma apenas se for válido e sucesso
        if (cert.status === 'Sucesso' && cert.valido) {
            if (cert.grupo.includes('1')) g1Total += cert.horas;
            else if (cert.grupo.includes('2')) g2Total += cert.horas;
        }

        row.innerHTML = `
            <td>${statusBadge}</td>
            <td>${cert.data || '--'}</td>
            <td><strong>${cert.fileName}</strong><br><small style="color:var(--gray)">${cert.assunto}</small></td>
            <td>${cert.grupo} - ${cert.categoria_ufpr || 'Indefinido'}</td>
            <td><strong>${cert.horas}h</strong></td>
            <td>
                 <button class="btn-small" onclick="removeCert('${cert.id}')">Remover</button>
            </td>
        `;
        tableBody.appendChild(row);
    });

    // Calcula final
    let g1Valido = Math.min(g1Total, 70); // Teto de 70h
    let g2Valido = Math.min(g2Total, 70); // Teto de 70h
    let totalGeral = g1Valido + g2Valido;

    // Atualiza Dashboards
    elTotalHours.innerHTML = `${totalGeral}h <span class="limit">/ 140h min</span>`;
    if(totalGeral >= 140) elTotalHours.style.color = 'var(--success)';
    else elTotalHours.style.color = '';

    elG1Hours.innerHTML = `${g1Total}h computadas <span class="limit">(Aproveitado: ${g1Valido}h)</span>`;
    elG2Hours.innerHTML = `${g2Total}h computadas <span class="limit">(Aproveitado: ${g2Valido}h)</span>`;
    
    progG1.style.width = Math.min((g1Valido / 70) * 100, 100) + '%';
    progG2.style.width = Math.min((g2Valido / 70) * 100, 100) + '%';
}

window.removeCert = function(id) {
    certificados = certificados.filter(c => c.id !== id);
    hashes_processados.delete(id);
    saveDashboard();
}
