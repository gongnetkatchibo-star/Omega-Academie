"""Pagination des grandes listes : on ne charge que la page demandée."""

from math import ceil

from flask import request, url_for
from markupsafe import Markup, escape

PAR_PAGE = 50


class Page:
    def __init__(self, elements, numero, nb_pages, total, par_page):
        self.elements = elements
        self.numero = numero
        self.nb_pages = nb_pages
        self.total = total
        self.par_page = par_page

    def __iter__(self):
        return iter(self.elements)

    def __len__(self):
        return len(self.elements)

    @property
    def premier(self):
        return (self.numero - 1) * self.par_page + 1 if self.total else 0

    @property
    def dernier(self):
        return self.premier + len(self.elements) - 1 if self.total else 0


def paginer(requete, par_page=PAR_PAGE):
    """Page courante (?page=N) d'une requête déjà triée."""
    total = requete.order_by(None).count()
    nb_pages = max(ceil(total / par_page), 1)
    numero = min(max(request.args.get("page", 1, type=int) or 1, 1), nb_pages)
    elements = requete.limit(par_page).offset((numero - 1) * par_page).all()
    return Page(elements, numero, nb_pages, total, par_page)


def paginer_liste(elements, par_page=PAR_PAGE):
    """Comme paginer(), pour une liste déjà calculée en mémoire (ex. la
    caisse, dont le solde cumulé demande de parcourir tous les mouvements)."""
    total = len(elements)
    nb_pages = max(ceil(total / par_page), 1)
    numero = min(max(request.args.get("page", 1, type=int) or 1, 1), nb_pages)
    debut = (numero - 1) * par_page
    return Page(elements[debut:debut + par_page], numero, nb_pages, total, par_page)


def liens_pagination(page):
    """Barre « Précédent / Suivant » qui conserve les filtres de l'adresse."""
    if page.nb_pages <= 1:
        return Markup(f'<p class="pagination-resume">{page.total} résultat(s)</p>') if page.total else Markup("")

    def lien(numero, libelle, actif=True):
        if not actif:
            return f'<span class="pagination-inactif">{escape(libelle)}</span>'
        arguments = {**request.view_args, **request.args.to_dict(), "page": numero}
        return f'<a href="{escape(url_for(request.endpoint, **arguments))}">{escape(libelle)}</a>'

    return Markup(
        '<nav class="pagination" aria-label="Pages">'
        + lien(page.numero - 1, "← Précédent", page.numero > 1)
        + f'<span class="pagination-resume">{page.premier}–{page.dernier} sur {page.total} · page {page.numero}/{page.nb_pages}</span>'
        + lien(page.numero + 1, "Suivant →", page.numero < page.nb_pages)
        + "</nav>"
    )
