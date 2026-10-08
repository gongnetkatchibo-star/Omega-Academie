"""Numéros WhatsApp selon le pays de l'école, et numéros internationaux."""

import pytest

from app.services.numeros import normaliser_numero, numero_lisible


@pytest.mark.parametrize("saisie, pays, attendu", [
    # Tchad : règle d'origine inchangée
    ("66 12 34 56", "Tchad", "+23566123456"),
    ("00235 99 88 77 66", "", "+23599887766"),
    ("22 51 00 00", "Tchad", None),            # fixe : pas sur WhatsApp
    ("6612345", "Tchad", None),
    # Cameroun
    ("6 90 11 22 33", "Cameroun", "+237690112233"),
    ("237690112233", "cameroun", "+237690112233"),
    ("69011223", "Cameroun", None),
    # Pays à préfixe national 0, pays à 10 chiffres
    ("0803 123 4567", "Nigeria", "+2348031234567"),
    ("07 07 12 34 56", "Côte d'Ivoire", "+2250707123456"),
    ("01 97 12 34 56", "Bénin", "+2290197123456"),
    # Numéro international saisi avec + ou 00, quelle que soit l'école
    ("+33 6 12 34 56 78", "Tchad", "+33612345678"),
    ("00237 6 90 11 22 33", "Tchad", "+237690112233"),
    ("+235 22 51 00 00", "Cameroun", None),    # tchadien fixe, même saisi en international
    ("", "Tchad", None),
    ("pas de numéro", "Cameroun", None),
])
def test_normaliser_numero(saisie, pays, attendu):
    assert normaliser_numero(saisie, pays) == attendu


def test_pays_inconnu_ou_vide_reste_le_tchad():
    assert normaliser_numero("66 12 34 56", "Atlantide") == "+23566123456"
    assert normaliser_numero("66 12 34 56", None) == "+23566123456"


def test_numero_lisible():
    assert numero_lisible("+23566123456") == "+235 66 12 34 56"
    assert numero_lisible("+237690112233") == "+237 690 11 22 33"
    assert numero_lisible("+33612345678") == "+33 612 34 56 78"
    assert numero_lisible("+2250707123456") == "+225 07 07 12 34 56"


def test_contacts_whatsapp_d_une_ecole_camerounaise(app, db, creer_classe, creer_eleve):
    from flask import g
    from app.models.ecole import Ecole
    from app.services.whatsapp import contacts

    ecole = db.session.get(Ecole, 1)
    ecole.pays = "Cameroun"
    db.session.commit()
    g.ecole_id = 1
    eleve = creer_eleve("Awa", creer_classe())
    eleve.telephone_parent = "6 90 11 22 33"
    eleve.personne_urgence, eleve.telephone_urgence = "Oncle à Paris", "+33 6 12 34 56 78"
    db.session.commit()

    assert [(c["nom"], c["numero"]) for c in contacts(eleve)] == [
        ("Téléphone du dossier", "+237690112233"),
        ("Oncle à Paris", "+33612345678"),
    ]
