import streamlit as st
import pdfplumber
import re
from typing import Tuple

st.set_page_config(page_title="Conferidor Fiscal - IN 1.234/2012", layout="wide")
st.title("🧾 Conferidor Fiscal - Retenções IN RFB 1.234/2012")
st.markdown("**Upload da NFS-e + Nota de Sistema + (opcional) Extrato de Conta Vinculada**")

# ===================== REGRAS DE ALÍQUOTAS =====================
regras = {
    "6190": {"aliquota": 9.45, "nome": "Demais serviços"},
    "8863": {"aliquota": 4.65, "nome": "Associações e cooperativas"},
    "6175": {"aliquota": 7.05, "nome": "Transporte de passageiros nacional"},
}

def classificar_servico(descricao: str) -> Tuple[str, float, str]:
    desc = descricao.upper()
    if any(palavra in desc for palavra in ["LIMPEZA", "MÃO DE OBRA", "SERVIÇOS CONTINUADOS", "LOCAÇÃO", "VIGILÂNCIA", "MANUTENÇÃO", "ELEVADOR", "ADMINISTRAÇÃO", "TEMPORÁRIOS", "EFETIVOS"]):
        return "6190", 9.45, "Demais serviços"
    if "COOPERATIVA" in desc or "ASSOCIAÇÃO" in desc:
        return "8863", 4.65, "Associações / Cooperativas"
    return "6190", 9.45, "Demais serviços (padrão)"

# ===================== FUNÇÕES DE EXTRAÇÃO =====================
def extrair_texto_pdf(arquivo) -> str:
    texto = ""
    with pdfplumber.open(arquivo) as pdf:
        for page in pdf.pages:
            texto += (page.extract_text() or "") + "\n"
    return texto

def identificar_tipo(texto: str) -> str:
    t = texto.upper()
    if "NFS-E" in t or "NOTA FISCAL DE SERVIÇOS" in t or "PREFEITURA" in t and "SERVIÇOS" in t:
        return "NFS"
    if "SIAFI" in t or "NOTA LANCAMENTO DE SISTEMA" in t or "NS" in t and "EVENTO" in t:
        return "NS"
    if "CONTA DEPÓSITO VINCULADA" in t or "PROVISÃO MENSAL" in t or "TOTAL A SER PROVISIONADO" in t:
        return "CONTA_VINCULADA"
    return "DESCONHECIDO"

def extrair_valores(texto: str):
    padrao = r'R\$\s*([\d.]+,\d{2})'
    valores = re.findall(padrao, texto)
    return [float(v.replace('.', '').replace(',', '.')) for v in valores]

def extrair_total_provisionado(texto: str):
    valores = extrair_valores(texto)
    return max(valores) if valores else None

# ===================== INTERFACE =====================
uploaded_files = st.file_uploader("Arraste ou selecione os PDFs", type=["pdf"], accept_multiple_files=True)

if st.button("🔍 Realizar Conferência", type="primary"):
    if len(uploaded_files) < 2:
        st.error("Você precisa enviar pelo menos a NFS-e e a Nota de Sistema.")
    else:
        docs = {}
        for file in uploaded_files:
            texto = extrair_texto_pdf(file)
            tipo = identificar_tipo(texto)
            docs[tipo] = {"nome": file.name, "texto": texto}

        nfs = docs.get("NFS")
        ns = docs.get("NS")
        conta_vinc = docs.get("CONTA_VINCULADA")

        if not nfs or not ns:
            st.error("Não foi possível identificar a NFS-e ou a Nota de Sistema.")
        else:
            st.success("Documentos identificados com sucesso!")

            # Conferência Padrão
            texto_nfs = nfs["texto"]
            valores_nfs = extrair_valores(texto_nfs)
            base_calculo = max(valores_nfs) if valores_nfs else None

            desc_servico = texto_nfs[:800]
            codigo, aliquota, nome_regra = classificar_servico(desc_servico)

            st.subheader("📋 Resultado da Conferência")
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**Serviço classificado:** {nome_regra}")
                st.write(f"**Alíquota esperada:** {aliquota}%")
            with col2:
                if base_calculo:
                    st.write(f"**Base de cálculo:** R$ {base_calculo:,.2f}")
                    retencao_esperada = round(base_calculo * aliquota / 100, 2)
                    st.write(f"**Retenção esperada:** R$ {retencao_esperada:,.2f}")

            # Conta Vinculada
            if conta_vinc:
                total_cv = extrair_total_provisionado(conta_vinc["texto"])
                st.subheader("🔗 Conta Vinculada Detectada")
                st.write(f"**Total provisionado:** R$ {total_cv:,.2f}" if total_cv else "Não foi possível extrair o total")
                
                if total_cv:
                    valores_ns = extrair_valores(ns["texto"])
                    encontrado = any(abs(total_cv - v) <= 50 for v in valores_ns)  # tolerância de R$ 50
                    if encontrado:
                        st.success("✅ Total da Conta Vinculada encontrado na Nota de Sistema")
                    else:
                        st.warning("⚠️ Total da Conta Vinculada NÃO encontrado na Nota de Sistema")

            st.info("Conferência finalizada. Caso precise de ajustes, me avise!")

st.caption("Conferidor Fiscal • Baseado na IN RFB 1.234/2012")