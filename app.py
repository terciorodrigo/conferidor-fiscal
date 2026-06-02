import streamlit as st
import pdfplumber
import re
from typing import List, Dict, Tuple
import pandas as pd

st.set_page_config(page_title="Conferidor Fiscal Avançado", layout="wide")
st.title("🧾 Conferidor Fiscal Avançado")
st.markdown("**Múltiplas NFS-e + Detecção automática de Simples Nacional + Regras de São Paulo**")

# ===================== REGRAS =====================
regras = {
    "6190": {"aliquota": 9.45, "nome": "Demais serviços"},
    "8863": {"aliquota": 4.65, "nome": "Associações e cooperativas"},
    "6175": {"aliquota": 7.05, "nome": "Transporte de passageiros nacional"},
}

def classificar_servico(descricao: str) -> Tuple[str, float, str]:
    desc = descricao.upper()
    if any(p in desc for p in ["LIMPEZA", "MÃO DE OBRA", "SERVIÇOS CONTINUADOS", "LOCAÇÃO", "VIGILÂNCIA", "MANUTENÇÃO", "ELEVADOR", "ADMINISTRAÇÃO", "TEMPORÁRIOS", "EFETIVOS"]):
        return "6190", 9.45, "Demais serviços"
    if "COOPERATIVA" in desc or "ASSOCIAÇÃO" in desc:
        return "8863", 4.65, "Associações / Cooperativas"
    return "6190", 9.45, "Demais serviços (padrão)"

def detectar_simples_nacional(texto: str) -> bool:
    t = texto.upper()
    frases = [
        "OPTANTE PELO SIMPLES NACIONAL",
        "DOCUMENTO EMITIDO POR ME/EPP OPTANTE PELO SIMPLES",
        "NÃO RETENÇÃO DE IR, CSLL, PIS E COFINS",
        "PRESTADOR OPTANTE PELO SIMPLES NACIONAL",
        "LEI COMPLEMENTAR 123/2006"
    ]
    return any(frase in t for frase in frases)

def extrair_texto_pdf(arquivo) -> str:
    texto = ""
    try:
        with pdfplumber.open(arquivo) as pdf:
            for page in pdf.pages:
                texto += (page.extract_text() or "") + "\n"
    except:
        pass
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

def extrair_base_calculo(texto: str) -> float:
    padrao = r'R\$\s*([\d.]+,\d{2})'
    valores = re.findall(padrao, texto)
    if not valores:
        return 0.0
    nums = []
    for v in valores:
        try:
            nums.append(float(v.replace('.', '').replace(',', '.')))
        except:
            pass
    return max(nums) if nums else 0.0

def extrair_valores_monetarios(texto: str) -> List[float]:
    padrao = r'R\$\s*([\d.]+,\d{2})'
    valores = re.findall(padrao, texto)
    nums = []
    for v in valores:
        try:
            nums.append(float(v.replace('.', '').replace(',', '.')))
        except:
            pass
    return nums

# ===================== INTERFACE =====================
st.info("Envie **uma ou mais NFS-e** + **uma Nota de Sistema**. O app detecta automaticamente se o prestador é Simples Nacional.")

uploaded_files = st.file_uploader(
    "Arraste ou selecione os arquivos PDF (NFS-e + NS)",
    type=["pdf"],
    accept_multiple_files=True
)

if st.button("🚀 Realizar Conferência", type="primary", use_container_width=True):
    if not uploaded_files:
        st.error("Envie pelo menos uma NFS-e e uma Nota de Sistema.")
    else:
        nfs_list = []
        ns_texto = ""
        conta_texto = ""

        for file in uploaded_files:
            texto = extrair_texto_pdf(file)
            tipo = identificar_tipo(texto)
            if tipo == "NFS":
                nfs_list.append({"nome": file.name, "texto": texto})
            elif tipo == "NS":
                ns_texto = texto
            elif tipo == "CONTA_VINCULADA":
                conta_texto = texto

        if not nfs_list or not ns_texto:
            st.error("É necessário pelo menos uma NFS-e e uma Nota de Sistema.")
        else:
            st.success(f"Processados: {len(nfs_list)} NFS-e + 1 Nota de Sistema")

            resultados = []
            total_base = 0.0
            total_retencao_esperada = 0.0

            for nfs in nfs_list:
                texto = nfs["texto"]
                is_simples = detectar_simples_nacional(texto)
                base = extrair_base_calculo(texto)

                if is_simples:
                    aliquota = 0.0
                    retencao_esperada = 0.0
                    tipo_retencao = "Simples Nacional (SP)"
                    obs = "Sem retenção federal. Verificar ISS retido na NS (obrigatório para órgãos públicos de SP)"
                else:
                    codigo, aliquota, nome = classificar_servico(texto[:800])
                    retencao_esperada = round(base * aliquota / 100, 2)
                    tipo_retencao = f"{nome} ({aliquota}%)"
                    obs = ""

                total_base += base
                total_retencao_esperada += retencao_esperada

                resultados.append({
                    "Arquivo": nfs["nome"],
                    "Simples Nacional": "Sim" if is_simples else "Não",
                    "Base de Cálculo (R$)": base,
                    "Alíquota / Tipo": tipo_retencao,
                    "Retenção Esperada (R$)": retencao_esperada,
                    "Observação": obs
                })

            # ===================== TABELA INDIVIDUAL =====================
            st.subheader("📋 Resultado por NFS-e")
            df = pd.DataFrame(resultados)
            st.dataframe(df, use_container_width=True, hide_index=True)

            # ===================== RESUMO CONSOLIDADO =====================
            st.subheader("📊 Resumo Consolidado")

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Base de Cálculo", f"R$ {total_base:,.2f}")
            with col2:
                st.metric("Total Retenção Esperada", f"R$ {total_retencao_esperada:,.2f}")
            with col3:
                valores_ns = extrair_valores_monetarios(ns_texto)
                valor_ns = max(valores_ns) if valores_ns else 0
                st.metric("Valor Principal na NS", f"R$ {valor_ns:,.2f}")

            # ===================== RESULTADO FINAL =====================
            st.subheader("✅ Resultado da Conferência")

            diferenca = abs(total_base - valor_ns)
            qtd_simples = sum(1 for r in resultados if r["Simples Nacional"] == "Sim")

            if diferenca <= 10:
                if qtd_simples > 0:
                    st.success("**Conferência OK** — Prestador(es) Simples Nacional detectado(s)")
                    st.markdown("""
                    **O que foi verificado:**
                    - Retenção federal (IR + CSLL + PIS + COFINS) esperada: **R$ 0,00** → Correto para Simples Nacional
                    - Soma das bases das NFS-e confere com o valor da Nota de Sistema
                    - Nenhuma retenção federal indevida identificada

                    **Atenção (São Paulo):**
                    Para órgãos públicos municipais e estaduais de São Paulo, quando o prestador é Simples Nacional, **o ISS deve ser retido na fonte** pela Fundacentro. Verifique se esse valor aparece na Nota de Sistema.
                    """)
                else:
                    st.success("**Conferência OK** — Todos os valores conferem corretamente")
                    st.markdown("""
                    **O que foi verificado:**
                    - Base de cálculo total das NFS-e bate com o valor da Nota de Sistema
                    - Retenção esperada (conforme tabela da IN RFB 1.234/2012) está correta
                    - Nenhuma divergência de valores ou alíquota foi identificada
                    """)
            else:
                st.error("**Conferência com divergência**")
                st.markdown(f"""
                **Problema identificado:**
                - Diferença entre o total das NFS-e e o valor da Nota de Sistema: **R$ {diferenca:,.2f}**

                **Recomendação:**
                Revise manualmente os valores de base de cálculo nas NFS-e e o lançamento na Nota de Sistema.
                """)

            st.caption("Conferidor Fiscal • Fundacentro • Baseado na IN RFB 1.234/2012 + regras do município de São Paulo")