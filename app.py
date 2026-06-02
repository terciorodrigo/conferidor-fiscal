import streamlit as st
import pdfplumber
import re
from typing import List, Dict, Tuple
import pandas as pd

st.set_page_config(page_title="Conferidor Fiscal Avançado", layout="wide")
st.title("🧾 Conferidor Fiscal Avançado (Debug Mode)")
st.markdown("**Versão com informações de extração para diagnóstico**")

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
    except Exception as e:
        st.warning(f"Erro ao ler {arquivo.name}: {e}")
    return texto

def identificar_tipo(texto: str) -> str:
    t = texto.upper()
    if "NFS-E" in t or "NOTA FISCAL DE SERVIÇOS" in t or ("PREFEITURA" in t and "SERVIÇOS" in t):
        return "NFS"
    if "SIAFI" in t or "NOTA LANCAMENTO DE SISTEMA" in t or ("NS" in t and "EVENTO" in t):
        return "NS"
    if "CONTA DEPÓSITO VINCULADA" in t or "PROVISÃO MENSAL" in t or "TOTAL A SER PROVISIONADO" in t:
        return "CONTA_VINCULADA"
    return "DESCONHECIDO"

def extrair_valores_monetarios(texto: str) -> List[float]:
    """Extrai todos os valores monetários (mais robusto)"""
    padrao = r'(?:R\$\s*)?([\d.]+,\d{2})'
    valores_str = re.findall(padrao, texto)
    nums = []
    for v in valores_str:
        try:
            nums.append(float(v.replace('.', '').replace(',', '.')))
        except:
            pass
    return nums

def extrair_base_calculo(texto: str) -> float:
    padroes = [
        r'VALOR TOTAL DO SERVIÇO\s*=\s*R?\$\s*([\d.]+,\d{2})',
        r'BASE DE CÁLCULO.*?R?\$\s*([\d.]+,\d{2})',
        r'VALOR TOTAL.*?R?\$\s*([\d.]+,\d{2})',
        r'FATURAMENTO.*?R?\$\s*([\d.]+,\d{2})',
    ]
    for padrao in padroes:
        match = re.search(padrao, texto, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1).replace('.', '').replace(',', '.'))
            except:
                pass

    valores = extrair_valores_monetarios(texto)
    return max(valores) if valores else 0.0

def extrair_valor_principal_ns(texto: str) -> float:
    valores = extrair_valores_monetarios(texto)
    return max(valores) if valores else 0.0

def classificar_servico(descricao: str) -> Tuple[str, float, str]:
    desc = descricao.upper()
    if any(p in desc for p in ["LIMPEZA", "MÃO DE OBRA", "SERVIÇOS CONTINUADOS", "LOCAÇÃO", "VIGILÂNCIA", "MANUTENÇÃO", "ELEVADOR", "ADMINISTRAÇÃO", "TEMPORÁRIOS", "EFETIVOS"]):
        return "6190", 9.45, "Demais serviços"
    if "COOPERATIVA" in desc or "ASSOCIAÇÃO" in desc:
        return "8863", 4.65, "Associações / Cooperativas"
    return "6190", 9.45, "Demais serviços (padrão)"

# ===================== INTERFACE =====================
st.info("**Modo Debug ativado** — O app mostra os valores que está extraindo de cada arquivo.")

uploaded_files = st.file_uploader(
    "Arraste os PDFs (NFS-e + NS)",
    type=["pdf"],
    accept_multiple_files=True
)

if st.button("🚀 Realizar Conferência", type="primary", use_container_width=True):
    if not uploaded_files:
        st.error("Envie pelo menos uma NFS-e e uma Nota de Sistema.")
    else:
        nfs_list = []
        ns_texto = ""

        for file in uploaded_files:
            texto = extrair_texto_pdf(file)
            tipo = identificar_tipo(texto)
            if tipo == "NFS":
                nfs_list.append({"nome": file.name, "texto": texto})
            elif tipo == "NS":
                ns_texto = texto

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
                    obs = "Sem retenção federal"
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
                    "Base Extraída (R$)": base,
                    "Alíquota / Tipo": tipo_retencao,
                    "Retenção Esperada (R$)": retencao_esperada,
                    "Observação": obs
                })

            # Tabela
            st.subheader("📋 Resultado por NFS-e (com valores extraídos)")
            df = pd.DataFrame(resultados)
            st.dataframe(df, use_container_width=True, hide_index=True)

            # Resumo
            st.subheader("📊 Resumo Consolidado")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Base Extraída (NFS-e)", f"R$ {total_base:,.2f}")
            with col2:
                st.metric("Retenção Esperada Total", f"R$ {total_retencao_esperada:,.2f}")
            with col3:
                valor_ns = extrair_valor_principal_ns(ns_texto)
                st.metric("Valor Principal Extraído (NS)", f"R$ {valor_ns:,.2f}")

            # Debug
            with st.expander("🔍 Informações de Debug"):
                st.write(f"**Base total extraída das NFS-e:** R$ {total_base:,.2f}")
                st.write(f"**Valor principal extraído da NS:** R$ {valor_ns:,.2f}")
                st.write(f"**Diferença:** R$ {abs(total_base - valor_ns):,.2f}")

            # Resultado Final
            st.subheader("✅ Resultado da Conferência")

            diferenca = abs(total_base - valor_ns)
            qtd_simples = sum(1 for r in resultados if r["Simples Nacional"] == "Sim")

            if diferenca <= 10:
                if qtd_simples > 0:
                    st.success("**Conferência OK** — Prestador(es) Simples Nacional detectado(s)")
                else:
                    st.success("**Conferência OK** — Todos os valores conferem corretamente")
            else:
                st.error("**Conferência com divergência**")
                st.markdown(f"""
                **Problema:** Diferença de **R$ {diferenca:,.2f}**.
                Verifique no Debug se o valor da NS está vindo correto.
                """)

            st.caption("Conferidor Fiscal • Fundacentro • IN RFB 1.234/2012 + regras município de São Paulo")
