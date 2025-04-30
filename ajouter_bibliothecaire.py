from Bibliosmart.app import db
from Bibliosmart.models import Bibliothecaire
import bcrypt

mot_de_passe = bcrypt.hashpw("admin123".encode('utf-8'), bcrypt.gensalt())

biblio = Bibliothecaire(nom="Admin", prenom="Principal", email="admin@biblio.com", mot_de_passe=mot_de_passe)
db.session.add(biblio)
db.session.commit()
print("Bibliothécaire ajouté")
