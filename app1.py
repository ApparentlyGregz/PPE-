import streamlit as st
import re
import fitz  # PyMuPDF pour PDF
from docx import Document
from io import BytesIO
from google import genai as gemini # Import de l'API Gemini

# ----------------------------------------------------------------------
# 1. Configuration de l'API Gemini
# ----------------------------------------------------------------------

# Déclare l'objet client pour qu'il existe dans le scope global
client = None 

try:
    # --- INSÉREZ VOTRE VRAIE CLÉ API GEMINI ICI ---
    # Remplacer "VOTRE_CLÉ_API_RÉELLE" par votre clé (ex: "AIza...")
    client = gemini.Client(api_key="AIzaSyAmuSaPfgHceLEvKGDOex2eCUSaEqwDNUg") 
except Exception as e:
    # Affiche l'erreur critique de l'API dans le terminal (pas sur l'interface)
    print(f"Erreur Critique: Impossible de se connecter à l'API Gemini. Détails: {e}")
    pass 

# ----------------------------------------------------------------------
# 2. Fonctions d'Extraction (PDF et DOCX)
# ----------------------------------------------------------------------

def extract_text_docx(uploaded_file):
    """Extrait le texte d'un fichier DOCX."""
    try:
        document = Document(uploaded_file)
        return "\n".join([paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()])
    except Exception as e:
        st.error(f"Erreur extraction DOCX : {e}")
        return ""

def extract_text_pdf(uploaded_file):
    """Extrait le texte d'un fichier PDF en utilisant PyMuPDF."""
    try:
        pdf_bytes = uploaded_file.read()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text() + "\n\n"
        return text.strip()
    except Exception as e:
        st.error(f"Erreur extraction PDF : {e}")
        return ""

# ----------------------------------------------------------------------
# 3. Fonction de Segmentation des Chapitres
# ----------------------------------------------------------------------

def segmenter_texte(document_text):
    """
    Découpe le texte en segments (chapitres) basés sur des patterns de titres numériques.
    """
    # Regex pour détecter les titres comme "1. Introduction", "2.1. Matériel", etc.
    pattern = r"^\s*(\d+(\.\d+)*\s[A-ZÉÈÀÂÎÔÙÛa-zéèàâîôùû].*)$"
    
    titres_indices = [(m.start(), m.group(1).strip()) for m in re.finditer(pattern, document_text, re.MULTILINE)]
    segments = []
    
    if not titres_indices:
        return [{"titre": "Document Complet / Pas de Segmentation", "texte": document_text}]

    for i, (start_index, titre) in enumerate(titres_indices):
        if i + 1 < len(titres_indices):
            end_index = titres_indices[i+1][0]
        else:
            end_index = len(document_text)
            
        texte_segment = document_text[start_index:end_index].replace(titre, "", 1).strip()
        
        if texte_segment:
            segments.append({"titre": titre, "texte": texte_segment})
            
    if titres_indices[0][0] > 0:
        texte_avant = document_text[:titres_indices[0][0]].strip()
        if texte_avant:
            segments.insert(0, {"titre": "0. Texte Préliminaire (Introduction, Remerciements)", "texte": texte_avant})

    return segments

# ----------------------------------------------------------------------
# 4. Fonction d'Appel à l'API Gemini (CORRIGÉE)
# ----------------------------------------------------------------------

def generer_questions_api(chapitres_segments):
    """Appelle l'API Gemini pour générer des questions pour chaque segment."""
    questions_par_chapitre = []
    
    base_prompt = """
    Role : Vous êtes un expert en pédagogie et en évaluation. Votre tâche est d'analyser le texte du chapitre ci-dessous et de générer une série de questions pertinentes pour évaluer la compréhension et la réflexion d'un étudiant.

    Objectif : Générer 5 questions au total :
    - 2 Questions de Compréhension (ex: Comment/Expliquez/Décrivez)
    - 2 Questions sur les Concepts Clés (ex: Définissez/Quel est le rôle de)
    - 1 Question de Réflexion Critique (ex: Quelles sont les limites/Comparez/Jugez l'efficacité)

    Format de Sortie : Fournissez uniquement une liste numérotée des questions (ex: "1. Expliquez...", "2. Quel est le rôle..."), sans aucune autre explication ou texte introductif.
    """
    
    if client is None:
        return [{"titre": "Erreur Critique", "questions": ["Le client Gemini n'est pas initialisé. Vérifiez votre clé API en Section 1 du code."]}];

    for chapitre in chapitres_segments:
        titre = chapitre['titre']
        texte_limite = chapitre['texte'][:10000] # Limite de caractères envoyés à l'API

        if not texte_limite:
             questions_par_chapitre.append({"titre": titre, "questions": ["(Aucun texte significatif trouvé pour ce chapitre.)"]})
             continue
        
        prompt_final = f"{base_prompt}\n\nTitre du Chapitre : {titre}\n\nTexte du Chapitre :\n{texte_limite}"

        try:
            # Appel correct à l'API Gemini
            response = client.models.generate_content(
                model='gemini-2.5-flash', 
                contents=prompt_final
            )
            
            questions_list = [q.strip() for q in response.text.split('\n') if q.strip()]

            questions_par_chapitre.append({"titre": titre, "questions": questions_list})
            
        except Exception as e:
            err_msg = f"Erreur API lors de la génération. Détail: {e}"
            questions_par_chapitre.append({"titre": titre, "questions": [err_msg]})

    return questions_par_chapitre

# ----------------------------------------------------------------------
# 5. Interface Streamlit (Application Principale)
# ----------------------------------------------------------------------

st.set_page_config(layout="wide", page_title="QG Pédagogique (PPE)")

st.title("🧠 Génération Automatique de Questions pour Rapports (PPE)")
st.caption("Prototype développé pour l'évaluation et l'auto-évaluation à partir de rapports PDF/DOCX.")

uploaded_file = st.file_uploader(
    "1. Choisissez votre Rapport de Stage (PDF ou DOCX)",
    type=['pdf', 'docx']
)

if uploaded_file is not None:
    
    # 2. Extraction du Texte
    file_type = uploaded_file.type
    if file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        document_text = extract_text_docx(uploaded_file)
    elif file_type == "application/pdf":
        document_text = extract_text_pdf(uploaded_file)
    else:
        document_text = ""
    
    if not document_text.strip():
        st.warning("Impossible d'extraire le texte du document. Veuillez vérifier le format.")
        st.stop()
        
    col1, col2 = st.columns([1, 1])

    # --- COLONNE 1 : Affichage du Document ---
    with col1:
        st.header("📖 Document Original (Texte Extrait)")
        st.text_area(
            "Contenu textuel du rapport (premiers caractères) :",
            document_text[:20000] + ("..." if len(document_text) > 20000 else ""),
            height=600,
            key="document_viewer"
        )
        
    # --- COLONNE 2 : Génération et Affichage des Questions ---
    with col2:
        st.header("❓ Questions Générées par Chapitre")
        
        # Ce bloc permet d'afficher les chapitres détectés avant de lancer l'IA (meilleure UX)
        chapitres_segments = segmenter_texte(document_text)
        st.info(f"Segmentation réussie : **{len(chapitres_segments)}** chapitres/sections détectés.")
        
        if st.button("2. Lancer la Génération des Questions", type="primary"):
            
            with st.spinner('Analyse, segmentation et appel à l\'IA en cours... (Durée variable selon la taille du rapport)'):
                
                # B. Génération des Questions
                questions_par_chapitre = generer_questions_api(chapitres_segments)
                
                # C. Affichage des Résultats
                for resultat in questions_par_chapitre:
                    st.subheader(f"✅ {resultat['titre']}")
                    questions_markdown = "\n".join(resultat['questions'])
                    st.markdown(questions_markdown)
                    st.markdown("---")
