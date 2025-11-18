import streamlit as st
import re
import fitz  # PyMuPDF pour PDF
from docx import Document
from io import BytesIO
from google import genai as gemini # Import de l'API Gemini


# -------------------------------------------
# -------------------------------------------
# -------------------------------------------
# -------------------------------------------
# -------------------------------------------
# -------------------------------------------
# -------------------------------------------
# -------------------------------------------
# -------------------------------------------
# py -m streamlit run app1.py
# -------------------------------------------
# -------------------------------------------
# -------------------------------------------
# -------------------------------------------
# -------------------------------------------
# -------------------------------------------
# -------------------------------------------
# -------------------------------------------
# ----------------------------------------------------------------------
# Déclare l'objet client pour qu'il existe dans le scope global
client = None 

try:
    # --- INSÉREZ VOTRE VRAIE CLÉ API GEMINI ICI ---
    # Remplacer "VOTRE_CLÉ_API_RÉELLE" par votre clé (ex: "AIza...")
    client = gemini.Client(api_key="AIzaSyAmuSaPfgHceLEvKGDOex2eCUSaEqwDNUg") 
except Exception as e:
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
# 3. Fonction de Segmentation des Chapitres (PAR IA)
# ----------------------------------------------------------------------

def segmenter_texte(document_text):
    """
    Utilise l'IA pour identifier les titres de chapitres pertinents et les extrait.
    """
    if client is None:
         # On ne peut pas utiliser l'IA si le client n'est pas initialisé
         return [{"titre": "Erreur : Client API non initialisé", "texte": document_text}]
    
    prompt_titres = f"""
    Le texte ci-dessous est un rapport de stage ou un projet étudiant.
    Votre tâche est d'analyser le contenu et de lister UNIQUEMENT les titres de sections qui représentent des chapitres ou parties substantielles et intéressantes pour l'évaluation (ex: Introduction, Problématique, État de l'art, Méthodologie, Résultats, Conclusion).
    
    Excluez les titres trop courts ou génériques (ex: Table des matières, Auteurs, Remerciements).
    
    Renvoyez la liste des titres détectés, chacun sur une nouvelle ligne, sans numérotation, sans explication ni texte additionnel.

    Texte du Rapport (Début):
    {document_text[:8000]} 
    """

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash', 
            contents=prompt_titres
        )
        titres_ia = [t.strip() for t in response.text.split('\n') if t.strip() and len(t.strip()) > 5]
        
        if not titres_ia:
            return [{"titre": "Document Complet / IA n'a pas détecté de chapitres", "texte": document_text}]

    except Exception as e:
        st.error(f"Erreur de l'API lors de la détection des titres : {e}")
        return [{"titre": "Erreur de Segmentation (Voir Erreur API)", "texte": document_text}]
        
    segments = []
    titres_trouves = []
    
    for titre_cible in titres_ia:
        pattern_recherche = re.escape(titre_cible)
        match = re.search(pattern_recherche, document_text, re.IGNORECASE | re.MULTILINE)
        if match and match.start() not in [item[0] for item in titres_trouves]:
             titres_trouves.append((match.start(), titre_cible))
    
    titres_trouves.sort(key=lambda x: x[0])
    
    if not titres_trouves:
         return [{"titre": "Document Complet / Titres IA non trouvables", "texte": document_text}]

    for i, (start_index, titre) in enumerate(titres_trouves):
        if i + 1 < len(titres_trouves):
            end_index = titres_trouves[i+1][0]
        else:
            end_index = len(document_text)
            
        texte_segment = document_text[start_index:end_index].strip()
        
        if texte_segment:
            segments.append({"titre": titre, "texte": texte_segment})

    if titres_trouves[0][0] > 0:
        texte_avant = document_text[:titres_trouves[0][0]].strip()
        if texte_avant:
            segments.insert(0, {"titre": "0. Texte Préliminaire (Avant le premier chapitre)", "texte": texte_avant})

    return segments

# ----------------------------------------------------------------------
# 4. Fonction d'Appel à l'API Gemini (Génération de Questions)
# ----------------------------------------------------------------------

def generer_questions_api(chapitres_segments):
    """Appelle l'API Gemini pour générer des questions pour chaque segment."""
    questions_par_chapitre = []
    
    base_prompt = """
    Role : Vous êtes un expert en pédagogie et en évaluation. Votre tâche est d'analyser le texte du chapitre ci-dessous et de générer une série de questions pertinentes pour évaluer la compréhension et la réflexion d'un étudiant. Le titre du chapitre est fourni pour vous aider à contextualiser.

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
        texte_limite = chapitre['texte'][:10000] 

        if not texte_limite:
             questions_par_chapitre.append({"titre": titre, "questions": ["(Aucun texte significatif trouvé pour ce chapitre.)"]})
             continue
        
        prompt_final = f"{base_prompt}\n\nTitre du Chapitre : {titre}\n\nTexte du Chapitre :\n{texte_limite}"

        try:
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

# Ajout de l'icône pour un look plus pro
st.set_page_config(layout="wide", page_title="QG Pédagogique (PPE)", page_icon="🧠")

st.title("🧠 Génération Automatique de Questions pour Rapports (PPE)")
st.caption("Prototype basé sur l'analyse de documents longs via l'API Gemini.")

uploaded_file = st.file_uploader(
    "1. Choisissez votre Rapport de Stage (PDF ou DOCX)",
    type=['pdf', 'docx']
)

if uploaded_file is not None:
    
    # Extraction du Texte
    file_type = uploaded_file.type
    if file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        document_text = extract_text_docx(uploaded_file)
    elif file_type == "application/pdf":
        document_text = extract_text_pdf(uploaded_file)
    else:
        document_text = ""
    
    if not document_text.strip():
        st.warning("Impossible d'extraire le texte du document.")
        st.stop()
        
    st.markdown("---")
        
    col1, col2 = st.columns([1, 1])

    # --- COLONNE 1 : Affichage du Document (Conteneur Scrollable) ---
    with col1:
        st.header("📖 Document Original (Texte Extrait)")
        
        # Le st.text_area avec hauteur fixe permet le scroll séparé
        st.text_area(
            "Contenu textuel du rapport :",
            document_text, # Afficher tout le texte (le contenu est scrollable)
            height=500,
            key="document_viewer"
        )
        
    # --- COLONNE 2 : Génération et Affichage des Questions (Conteneur Scrollable) ---
    with col2:
        st.header("❓ Questions Générées par Chapitre")
        
        # 1. Analyse/Segmentation (effectuée à chaque upload)
        with st.spinner('Étape 1/2 : Analyse par l\'IA pour détecter les chapitres pertinents...'):
            chapitres_segments = segmenter_texte(document_text)
            
        st.info(f"Segmentation réussie : **{len(chapitres_segments)}** chapitres/sections détectés par l'IA.")
        
        if st.button("2. Lancer la Génération des Questions", type="primary"):
            
            # Utilisation d'un conteneur scrollable pour les résultats
            results_container = st.container(height=500) 

            with st.spinner('Étape 2/2 : Génération des questions pour chaque chapitre détecté...'):
                
                # B. Génération des Questions
                questions_par_chapitre = generer_questions_api(chapitres_segments)
                
                # C. Affichage des Résultats dans le conteneur scrollable
                with results_container:
                    for resultat in questions_par_chapitre:
                        st.subheader(f"✅ {resultat['titre']}")
                        questions_markdown = "\n".join(resultat['questions'])
                        st.markdown(questions_markdown)
                        st.markdown("---")
