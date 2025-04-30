from flask import Flask, render_template, request, redirect, url_for, session, flash 
from flask_migrate import Migrate
from models import db, Utilisateur, Livre, Emprunt, Paiement, Bibliothecaire, Notification
from db import init_db
import os
import bcrypt
from flask import jsonify
from datetime import datetime
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import smtplib
from email.message import EmailMessage
import random

def envoyer_code_verification(email, code):
    try:
        msg = EmailMessage()
        msg.set_content(f"Votre code de vérification est : {code}")
        msg['Subject'] = "Code de vérification - BiblioSmart"
        msg['From'] = "lynceeunice@gmail.com"
        msg['To'] = email

        with smtplib.SMTP('smtp.gmail.com', 587) as smtp:
            smtp.starttls()
            smtp.login('melisadasnay930@gmail.com', 'mray jjli lgku xizo')
            smtp.send_message(msg)
    except Exception as e:
        print("Erreur envoi mail :", e)

# Initialisation de l'application Flask
app = Flask(__name__)
app.secret_key = 'cle_secrete_bibliosmart'

# Configuration base de données
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///bibliosmart.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configuration dossier upload
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Initialisation extensions
db.init_app(app)
migrate = Migrate(app, db)
init_db(app)

# ================= ROUTES =================

@app.route('/')
@app.route('/accueil')
def home():
    return render_template('accueil.html')

@app.route('/login-bibliothecaire', methods=['GET', 'POST'])
def login_bibliothecaire():
    if request.method == 'POST':
        email = request.form['email']
        mot_de_passe = request.form['mot_de_passe'].encode('utf-8')
        biblio = Bibliothecaire.query.filter_by(email=email).first()
        if biblio and bcrypt.checkpw(mot_de_passe, biblio.mot_de_passe):
            session['biblio_id'] = biblio.id
            return redirect(url_for('espace_bibliothecaire'))
        else:
            flash("Identifiants incorrects")
    return render_template('login_bibliothecaire.html')

@app.route('/register-bibliothecaire', methods=['GET', 'POST'])
def register_bibliothecaire():
    if request.method == 'POST':
        nom = request.form['nom']
        prenom = request.form['prenom']
        email = request.form['email']
        mot_de_passe = request.form['mot_de_passe']

        if Bibliothecaire.query.filter_by( email= email).first():
            flash("Un compte avec cet email existe déjà.", "danger")
            return redirect(url_for('register_bibliothecaire'))

        hashed_pw = bcrypt.hashpw(mot_de_passe.encode('utf-8'), bcrypt.gensalt())

        nouveau_biblio = Bibliothecaire(
            nom=nom,
            prenom=prenom,
            email= email,
            mot_de_passe=hashed_pw
        )
        db.session.add(nouveau_biblio)
        db.session.commit()

        flash("Compte bibliothécaire créé avec succès !", "success")
        return redirect(url_for('login_bibliothecaire'))

    return render_template('register_bibliothecaire.html')


@app.route('/espace-bibliothecaire')
def espace_bibliothecaire():
    if 'biblio_id' not in session:
        return redirect(url_for('login_bibliothecaire'))

    livres = Livre.query.all()
    utilisateurs = Utilisateur.query.all()
    emprunts = Emprunt.query.all()
    paiements = Paiement.query.all()

    total_livres = Livre.query.count()
    livres_disponibles = Livre.query.filter_by(disponible=True).count()
    total_emprunts = Emprunt.query.count()

    # Top 3 livres les plus empruntés (par ID de livre)
    from sqlalchemy import func
    top_livres = db.session.query(
        Emprunt.livre_id, func.count(Emprunt.id).label('nb')
    ).group_by(Emprunt.livre_id).order_by(func.count(Emprunt.id).desc()).limit(3).all()

    # On cherche les livres associés aux ID
    top_livre_infos = [(Livre.query.get(livre_id), nb) for livre_id, nb in top_livres]

    # Pénalité fixe pour les retards
    PENALITE_PAR_JOUR = 1.0
    penalites = {}

    for emprunt in emprunts:
        if hasattr(emprunt, 'date_retour') and emprunt.date_retour:
            try:
                date_retour = datetime.strptime(emprunt.date_retour, "%Y-%m-%d")
                date_emprunt = datetime.strptime(emprunt.date_emprunt, "%Y-%m-%d")
                delta = (date_retour - date_emprunt).days
                if delta > 14:
                    jours_retard = delta - 14
                    penalites[emprunt.utilisateur_id] = penalites.get(emprunt.utilisateur_id, 0) + jours_retard * PENALITE_PAR_JOUR
            except Exception as e:
                print(f"Erreur lors du calcul de la pénalité pour l'emprunt {emprunt.id} : {e}")

    return render_template(
        'espace_bibliothecaire.html',
        livres=livres,
        utilisateurs=utilisateurs,
        emprunts=emprunts,
        paiements=paiements,
        total_livres=total_livres,
        livres_disponibles=livres_disponibles,
        total_emprunts=total_emprunts,
        top_livre_infos=top_livre_infos,
        penalites=penalites
    )


@app.route('/ajouter-notification', methods=['GET', 'POST'])
def ajouter_notification():
    if 'biblio_id' not in session:
        return redirect(url_for('login_bibliothecaire'))

    if request.method == 'POST':
        titre = request.form['titre']
        contenu = request.form['contenu']
        notif = Notification(titre=titre, contenu=contenu)
        db.session.add(notif)
        db.session.commit()
        flash("Notification ajoutée.")
        return redirect(url_for('espace_bibliothecaire'))

    return render_template('ajouter_notification.html')

@app.route('/ajouter-livre', methods=['GET', 'POST'])
def ajouter_livre():
    if 'biblio_id' not in session:
        return redirect(url_for('login_bibliothecaire'))

    if request.method == 'POST':
        titre = request.form['titre']
        auteur = request.form['auteur']
        categorie = request.form['categorie']
        date_publication = request.form['date_publication']
        isbn = request.form.get('isbn')
        image = request.form.get('image')

        nouveau_livre = Livre(
            titre=titre,
            auteur=auteur,
            categorie=categorie,
            date_publication=date_publication,
            disponible=True,
            isbn=isbn,
            image=image
        )
        db.session.add(nouveau_livre)
        db.session.commit()
        flash("Livre ajouté avec succès")
        return redirect(url_for('espace_bibliothecaire'))

    return render_template('ajouter_livre.html')



@app.route('/logout-bibliothecaire')
def logout_bibliothecaire():
    session.pop('biblio_id', None)
    flash("Déconnecté.")
    return redirect(url_for('login_bibliothecaire'))


@app.route('/modifier-livre/<int:livre_id>', methods=['GET', 'POST'])
def modifier_livre(livre_id):
    if 'biblio_id' not in session:
        return redirect(url_for('login_bibliothecaire'))

    livre = Livre.query.get_or_404(livre_id)

    if request.method == 'POST':
        livre.titre = request.form['titre']
        livre.auteur = request.form['auteur']
        livre.categorie = request.form['categorie']
        livre.disponible = 'disponible' in request.form
        db.session.commit()
        flash("Livre modifié avec succès")
        return redirect(url_for('espace_bibliothecaire'))

    return render_template('modifier_livre.html', livre=livre)


@app.route('/supprimer-livre/<int:livre_id>', methods=['POST'])
def supprimer_livre(livre_id):
    if 'biblio_id' not in session:
        return redirect(url_for('login_bibliothecaire'))

    livre = Livre.query.get_or_404(livre_id)
    db.session.delete(livre)
    db.session.commit()
    flash("Livre supprimé")
    return redirect(url_for('espace_bibliothecaire'))

@app.route('/utilisateur/<int:id>')
def details_utilisateur(id):
    if 'biblio_id' not in session:
        return redirect(url_for('login_bibliothecaire'))

    utilisateur = Utilisateur.query.get_or_404(id)
    emprunts = Emprunt.query.filter_by(utilisateur_id=id).all()

    return render_template('details_utilisateur.html', utilisateur=utilisateur, emprunts=emprunts)


@app.route('/register-lecteur', methods=['GET', 'POST'])
def register_lecteur():
    if request.method == 'POST':
        nom = request.form['nom']
        email = request.form['email']
        password = request.form['password']

        if Utilisateur.query.filter_by(email=email).first():
            flash("Cet email est déjà utilisé.", "danger")
            return redirect(url_for('register_lecteur'))

        hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        nouvel_utilisateur = Utilisateur(
            nom=nom,
            email=email,
            mot_de_passe=hashed_pw
        )

        db.session.add(nouvel_utilisateur)
        db.session.commit()

        flash("Compte créé avec succès! Bienvenue sur BiblioSmart 📚", "success")
        return redirect(url_for('compte_lecteur', utilisateur_id=nouvel_utilisateur.id))

    return render_template('register_lecteur.html')

@app.route('/login-lecteur', methods=['GET', 'POST'])
def login_lecteur():
    if request.method == 'POST':
        email = request.form['email']
        mot_de_passe = request.form['mot_de_passe']
        utilisateur = Utilisateur.query.filter_by(email=email).first()

        if utilisateur and bcrypt.checkpw(mot_de_passe.encode('utf-8'), utilisateur.mot_de_passe):
            code = str(random.randint(100000, 999999))
            session['email_temp'] = email
            session['code_verification'] = code
            envoyer_code_verification(email, code)
            flash("Un code de vérification vous a été envoyé par email.", "info")
            return redirect(url_for('verifier_code'))
        else:
            flash("Email ou mot de passe incorrect.", "danger")
    return render_template('login_lecteur.html')

@app.route('/verifier-code', methods=['GET', 'POST'])
def verifier_code():
    if request.method == 'POST':
        code_saisi = request.form['code']
        if code_saisi == session.get('code_verification'):
            utilisateur = Utilisateur.query.filter_by(email=session['email_temp']).first()
            if utilisateur:
                session['utilisateur_id'] = utilisateur.id
                flash("Connexion réussie.", "success")
                return redirect(url_for('compte_lecteur', utilisateur_id=utilisateur.id))
        flash("Code incorrect.", "danger")
    return render_template('verifier_code.html')

@app.route('/compte-lecteur/<int:utilisateur_id>')
def compte_lecteur(utilisateur_id):
    utilisateur = Utilisateur.query.get_or_404(utilisateur_id)
    return render_template("compte_lecteur.html", utilisateur=utilisateur)

@app.route('/rechercher-livre', methods=['GET'])
def rechercher_livre():
    query = request.args.get('query', '')
    livres = Livre.query.filter(
        (Livre.titre.ilike(f'%{query}%')) |
        (Livre.auteur.ilike(f'%{query}%')) |
        (Livre.categorie.ilike(f'%{query}%'))
    ).all()
    return render_template("recherche_resultats.html", livres=livres, query=query)

# Route correcte pour le catalogue
@app.route('/livres')
def catalogue():
    livres = Livre.query.all()
    return render_template('catalogue.html', livres=livres)

@app.route('/logout')
def logout():
    session.clear()
    flash("Vous avez été déconnecté.", "info")
    return redirect(url_for('register_lecteur'))

@app.route('/reserver-livre')
def reserver_livres():
    livres_disponibles = Livre.query.filter_by(disponible=True).all()
    return render_template("reserver_livres.html", livres=livres_disponibles)

@app.route('/emprunter-livres')
def emprunter_livres():
    utilisateur_id = session.get('utilisateur_id')
    if not utilisateur_id:
        flash("Veuillez vous connecter d'abord.", "warning")
        return redirect(url_for('login_lecteur'))

    utilisateur = Utilisateur.query.get(utilisateur_id)
    livres_empruntes = utilisateur.livres_empruntes  # si ou gen relation déjà
    return render_template("emprunter_livres.html", livres=livres_empruntes, utilisateur=utilisateur)

@app.route('/consulter-livres')
def consulter_livres():
    livres = Livre.query.all()
    return render_template('consulter_livres.html', livres=livres)

@app.route('/retourner-livre/<int:emprunt_id>', methods=['POST'])
def retourner_livre(emprunt_id):
    emprunt = Emprunt.query.get_or_404(emprunt_id)
    db.session.delete(emprunt)
    db.session.commit()
    return redirect(url_for('compte_lecteur', utilisateur_id=emprunt.utilisateur_id))

@app.route('/livres-empruntes')
def livres_empruntes():
    utilisateur_id = session.get('utilisateur_id')
    if not utilisateur_id:
        flash("Veuillez vous connecter.", "warning")
        return redirect(url_for('login_lecteur'))

    utilisateur = Utilisateur.query.get_or_404(utilisateur_id)
    emprunts = Emprunt.query.filter_by(utilisateur_id=utilisateur.id).all()
    return render_template('livres_empruntes.html', utilisateur=utilisateur, emprunts=emprunts)

@app.route('/payer-amende')
def payer_amende():
    return render_template('payer_amende.html')


@app.route('/chatbot', methods=['POST'])
def chatbot_response():
    data = request.get_json()
    message = data.get('message', '').strip()
 
    if not message:
        return jsonify({'response': "Je n'ai pas compris votre question 😅"})
 
    llm = ChatOpenAI(model="gpt-3.5-turbo")
    prompt = ChatPromptTemplate.from_template("""
    Tu es BiblioBot 🤖, un assistant de bibliothèque intelligent. Aide l'utilisateur de manière claire, concise et amicale.
    Voici sa question : {user_question}
    """)
    chain = prompt | llm | StrOutputParser()
 
    try:
        result = chain.invoke({"user_question": message})
        return jsonify({'response': result})
    except Exception as e:
        return jsonify({'response': f"Erreur lors de la réponse : {str(e)}"})
 

    # Vérifier d'abord s'il existe une correspondance exacte avec un titre
    livre_exact = Livre.query.filter(Livre.titre.ilike(message)).first()

    if livre_exact:
        response = (f"📖 Voici le livre que vous cherchez : '{livre_exact.titre}' "
                    f"par {livre_exact.auteur}. Souhaitez-vous le réserver ou l'ajouter à votre panier ?")
    elif livres:
        response = "📚 Voici quelques livres qui pourraient vous intéresser :\n"
        for livre in livres[:5]:
            response += f"- {livre.titre} par {livre.auteur}\n"
        response += "Souhaitez-vous réserver l'un de ces livres ?"
    elif "aide" in message:
        response = ("Vous pouvez rechercher un livre en précisant son titre, son auteur ou sa catégorie. "
                    "Si vous avez besoin d'aide pour autre chose, n'hésitez pas à me le dire !")
    elif "bonjour" in message or "salut" in message:
        response = "Bonjour ! Je suis BiblioBot 🤖. Comment puis-je vous aider aujourd'hui ?"
    elif "merci" in message:
        response = "Je vous en prie, c'est avec plaisir ! 😊"
    else:
        response = ("Je suis désolé, mais je n'ai pas trouvé de résultats pour votre recherche 😅. "
                    "Pourriez-vous reformuler votre demande ou préciser votre recherche ?")

    
    return jsonify({'response': response})



# ================= LANCEMENT =================
if __name__ == '__main__':
    app.run(debug=True)
