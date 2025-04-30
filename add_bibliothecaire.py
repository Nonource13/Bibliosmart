from app import app, db
from models import Bibliothecaire
import bcrypt

with app.app_context():
    email = "lisa@gmail.com"
    mot_de_passe = "test123"  # Mot de passe temporaire
    nom = "Lisa"
    prenom = "Dupont"

    # Vérifie si déjà existant
    if not Bibliothecaire.query.filter_by(email=email).first():
        hashed_pw = bcrypt.hashpw(mot_de_passe.encode('utf-8'), bcrypt.gensalt())
        nouveau = Bibliothecaire(nom=nom, prenom=prenom, email=email, mot_de_passe=hashed_pw)
        db.session.add(nouveau)
        db.session.commit()
        print("✅ Bibliothécaire ajouté avec succès !")
    else:
        print("⚠️ Un bibliothécaire avec cet email existe déjà.")
