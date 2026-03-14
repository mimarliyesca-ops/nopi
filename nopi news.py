#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔═══════════════════════════════════════════════════════════════╗
║              NOPI BOT — Version 3.0 Ultra                     ║
║         Assistant d'Information Premium & Culture             ║
║                 Développé par BenzoXDev 🚀                    ║
╠═══════════════════════════════════════════════════════════════╣
║  Nouveautés V3 :                                              ║
║  • 🚨 Alerte "Actualité Importante" automatique               ║
║  • 📊 Statistiques détaillées du bot                          ║
║  • 🔍 Commande /recherche avec mots-clés                      ║
║  • 🖼  Images automatiques des articles                        ║
║  • 💾 Persistance JSON (stats + abonnés notifs)               ║
║  • ⏰ Planificateur de tâches (breaking news toutes 30 min)   ║
╚═══════════════════════════════════════════════════════════════╝

INSTALLATION :
  pip install python-telegram-bot feedparser deep-translator requests

LANCEMENT :
  python Nopi_Bot_V3.py
"""

# ══════════════════════════════════════════════════════
#  IMPORTS
# ══════════════════════════════════════════════════════
import logging
import feedparser
import re
import html as html_lib
import json
import os
import asyncio
import requests
from io import BytesIO
from datetime import datetime, timedelta
from collections import defaultdict

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    BotCommand, InputMediaPhoto,
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError

# ── Traduction (optionnelle) ───────────────────────────
try:
    from deep_translator import GoogleTranslator
    TRANSLATION_OK = True
except ImportError:
    TRANSLATION_OK = False

# ══════════════════════════════════════════════════════
#  CONFIGURATION GLOBALE
# ══════════════════════════════════════════════════════
TOKEN            = "8614308353:AAEorFC6XjUFLBKIky1YeRcoNX8HAVcuqww"   # ← Remplacez par votre token BotFather
MAX_ARTICLES     = 4                   # Articles par requête flux
MAX_RECHERCHE    = 6                   # Articles max par /recherche
BOT_VERSION      = "3.0 Ultra"
BOT_AUTHOR       = "@benzoXdev"
STATS_FILE       = "nopi_stats.json"   # Fichier de sauvegarde des stats
BREAKING_INTERVAL= 1800                # Vérification breaking news (sec) = 30 min
# Mots-clés déclenchant une alerte "actualité importante" (titre en minuscules)
BREAKING_KEYWORDS = [
    "urgent", "breaking", "alerte", "flash", "direct",
    "guerre", "war", "attack", "attaque", "attentat",
    "earthquake", "séisme", "tremblement", "tsunami",
    "explosion", "crash", "catastrophe", "hurricane",
    "death", "mort", "killed", "dead", "assassin",
    "nuclear", "nucléaire", "crisis", "crise",
]

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("NoPi-V3")

# ══════════════════════════════════════════════════════
#  ÉTAT GLOBAL (en mémoire + sauvegarde JSON)
# ══════════════════════════════════════════════════════
# Structure des stats
_stats_defaut = {
    "utilisateurs_uniques": [],      # liste de user_id
    "total_requetes"      : 0,
    "requetes_par_cat"    : {},      # {cle: nb}
    "recherches"          : 0,
    "demarrage"           : datetime.now().isoformat(),
    "abonnes_notifs"      : [],      # user_id abonnés aux breaking news
    "breaking_envoyes"    : [],      # titres déjà envoyés (évite doublons)
}

def charger_stats() -> dict:
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Assure la compatibilité avec les anciennes versions
                for cle, val in _stats_defaut.items():
                    data.setdefault(cle, val)
                return data
        except Exception:
            pass
    return dict(_stats_defaut)

def sauvegarder_stats(stats: dict) -> None:
    try:
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.warning("Impossible de sauvegarder les stats : %s", exc)

# Chargement au démarrage
STATS = charger_stats()
STATS["demarrage"] = datetime.now().isoformat()  # Reset au démarrage


# ══════════════════════════════════════════════════════
#  CATALOGUE DES FLUX RSS
# ══════════════════════════════════════════════════════
FEEDS = {
    # ── Actualités par pays ────────────────────────────
    "France": {
        "url" : "https://www.lemonde.fr/rss/une.xml",
        "icon": "🇫🇷", "lang": "fr",
        "desc": "Le Monde — À la une",
    },
    "USA": {
        "url" : "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
        "icon": "🇺🇸", "lang": "en",
        "desc": "New York Times — Monde",
    },
    "Russie": {
        "url" : "https://www.rt.com/rss/news/",
        "icon": "🇷🇺", "lang": "en",
        "desc": "RT — Actualités mondiales",
    },
    "Monde": {
        "url" : "https://feeds.bbci.co.uk/news/world/rss.xml",
        "icon": "🌎", "lang": "en",
        "desc": "BBC News — Monde",
    },
    "Asie": {
        "url" : "https://feeds.bbci.co.uk/news/world/asia/rss.xml",
        "icon": "🌏", "lang": "en",
        "desc": "BBC News — Asie",
    },
    "Moyen-Orient": {
        "url" : "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml",
        "icon": "🕌", "lang": "en",
        "desc": "BBC News — Moyen-Orient",
    },
    "Europe": {
        "url" : "https://feeds.bbci.co.uk/news/world/europe/rss.xml",
        "icon": "🇪🇺", "lang": "en",
        "desc": "BBC News — Europe",
    },
    "Afrique": {
        "url" : "https://feeds.bbci.co.uk/news/world/africa/rss.xml",
        "icon": "🌍", "lang": "en",
        "desc": "BBC News — Afrique",
    },
    # ── Catégories thématiques ─────────────────────────
    "Science": {
        "url" : "https://www.sciencedaily.com/rss/top/science.xml",
        "icon": "🔬", "lang": "en",
        "desc": "ScienceDaily — Sciences",
    },
    "Technologie": {
        "url" : "https://techcrunch.com/feed/",
        "icon": "💻", "lang": "en",
        "desc": "TechCrunch",
    },
    "Santé": {
        "url" : "https://www.who.int/rss-feeds/news-releases-en.xml",
        "icon": "🏥", "lang": "en",
        "desc": "OMS — Santé mondiale",
    },
    "Environnement": {
        "url" : "https://www.theguardian.com/environment/rss",
        "icon": "🌿", "lang": "en",
        "desc": "The Guardian — Environnement",
    },
    "Culture": {
        "url" : "https://www.theguardian.com/culture/rss",
        "icon": "🎭", "lang": "en",
        "desc": "The Guardian — Culture",
    },
    "Économie": {
        "url" : "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines",
        "icon": "💹", "lang": "en",
        "desc": "MarketWatch",
    },
    "Sport": {
        "url" : "https://www.skysports.com/rss/12040",
        "icon": "⚽", "lang": "en",
        "desc": "Sky Sports",
    },
    "Espace": {
        "url" : "https://www.nasa.gov/rss/dyn/breaking_news.rss",
        "icon": "🚀", "lang": "en",
        "desc": "NASA — Nouvelles",
    },
    "IA & Robotique": {
        "url" : "https://techcrunch.com/category/artificial-intelligence/feed/",
        "icon": "🤖", "lang": "en",
        "desc": "TechCrunch — Intelligence Artificielle",
    },
    "Crypto": {
        "url" : "https://cointelegraph.com/rss",
        "icon": "₿", "lang": "en",
        "desc": "CoinTelegraph — Crypto & Blockchain",
    },
    # ── Vidéos YouTube ─────────────────────────────────
    "Vidéos_DW_FR": {
        "url" : "https://www.youtube.com/feeds/videos.xml?channel_id=UC4fsi7A2MFQN5tBrEGv0TFg",
        "icon": "📺", "lang": "fr",
        "desc": "DW Actualités Français — YouTube",
        "video": True,
    },
    "Vidéos_Science": {
        "url" : "https://www.youtube.com/feeds/videos.xml?channel_id=UCVHkD0sKvgArPyIJB7gNpBQ",
        "icon": "🔭", "lang": "fr",
        "desc": "Science étonnante — YouTube",
        "video": True,
    },
    "Vidéos_Monde": {
        "url" : "https://www.youtube.com/feeds/videos.xml?channel_id=UCknLrEdhRCp1aegoMqRaCZg",
        "icon": "🌍", "lang": "en",
        "desc": "DW News — YouTube",
        "video": True,
    },
}

# Flux utilisés pour la détection des breaking news
FEEDS_BREAKING = ["Monde", "USA", "France", "Russie", "Europe"]

# Groupes de navigation
MENU_PAYS       = ["France", "USA", "Russie", "Monde", "Asie",
                   "Moyen-Orient", "Europe", "Afrique"]
MENU_CATEGORIES = ["Science", "Technologie", "Santé", "Environnement",
                   "Culture", "Économie", "Sport", "Espace",
                   "IA & Robotique", "Crypto"]
MENU_VIDEOS     = ["Vidéos_DW_FR", "Vidéos_Science", "Vidéos_Monde"]


# ══════════════════════════════════════════════════════
#  UTILITAIRES TEXTE
# ══════════════════════════════════════════════════════
def nettoyer_html(texte: str) -> str:
    if not texte:
        return ""
    texte = html_lib.unescape(texte)
    texte = re.sub(r"<[^>]+>", " ", texte)
    texte = re.sub(r"\s{2,}", " ", texte).strip()
    return texte

def traduire_fr(texte: str, lang: str = "en") -> str:
    if not TRANSLATION_OK or lang == "fr" or not texte or not str(texte).strip():
        return texte
    try:
        # On convertit en chaîne et on limite la taille pour le traducteur (max 5000 chars)
        texte_propre = f"{texte}"[:4990]
        return GoogleTranslator(source=lang, target="fr").translate(texte_propre)
    except Exception as e:
        logger.warning("Traduction échouée : %s", e)
        return texte

def formater_date(entry) -> str:
    try:
        ts = entry.get("published_parsed") or entry.get("updated_parsed")
        if ts:
            return datetime(*ts[:6]).strftime("📅 %d/%m/%Y à %H:%M")
    except Exception:
        pass
    return ""

def securiser_md(texte: str) -> str:
    """Échappe les caractères Markdown V1 dangereux sans toucher * et _."""
    for c in ["[", "]", "(", ")"]:
        texte = texte.replace(c, f"\\{c}")
    return texte


# ══════════════════════════════════════════════════════
#  EXTRACTION D'IMAGE DEPUIS UNE ENTRÉE RSS
# ══════════════════════════════════════════════════════
def extraire_image_url(entry) -> str | None:
    """
    Cherche une image dans l'entrée RSS dans cet ordre :
    1. media_content  2. media_thumbnail  3. enclosures  4. <img> dans summary
    Retourne l'URL si trouvée et accessible, sinon None.
    """
    url = None

    # 1. media:content
    media = entry.get("media_content", [])
    if media and isinstance(media, list):
        for m in media:
            u = m.get("url", "")
            if u and re.search(r"\.(jpg|jpeg|png|webp|gif)", u, re.I):
                url = u
                break

    # 2. media:thumbnail
    if not url:
        thumb = entry.get("media_thumbnail", [])
        if thumb and isinstance(thumb, list):
            url = thumb[0].get("url")

    # 3. enclosures (podcasts/RSS avec pièces jointes)
    if not url:
        for enc in entry.get("enclosures", []):
            t = enc.get("type", "")
            if "image" in t:
                url = enc.get("href") or enc.get("url")
                break

    # 4. Scraping basique du HTML du résumé
    if not url:
        summary_raw = entry.get("summary", "") or entry.get("content", [{}])[0].get("value", "")
        match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', summary_raw)
        if match:
            url = match.group(1)

    # Vérification rapide de l'accessibilité (timeout 3s)
    if url:
        try:
            r = requests.head(url, timeout=3, allow_redirects=True)
            if r.status_code == 200 and "image" in r.headers.get("content-type", ""):
                return url
        except Exception:
            pass

    return None


# ══════════════════════════════════════════════════════
#  RÉCUPÉRATION D'ARTICLES RSS  (avec image)
# ══════════════════════════════════════════════════════
def recuperer_articles(cle: str) -> list[dict]:
    """
    Retourne une liste de dict :
      {
        "texte"   : str   — message formaté Markdown
        "image"   : str|None — URL image ou None
        "lien"    : str   — URL article
        "titre_brut": str — titre non traduit (pour recherche)
        "est_breaking": bool
      }
    """
    config = FEEDS.get(cle)
    if not config:
        return [{"texte": "❌ Source inconnue.", "image": None, "lien": "",
                 "titre_brut": "", "est_breaking": False}]

    try:
        feed = feedparser.parse(config["url"])
    except Exception as exc:
        logger.error("feedparser (%s) : %s", cle, exc)
        return [{"texte": f"❌ Source inaccessible : *{cle}*",
                 "image": None, "lien": "", "titre_brut": "", "est_breaking": False}]

    if not feed.entries:
        return [{"texte": "⚠️ Aucun article disponible.", "image": None, "lien": "",
                 "titre_brut": "", "est_breaking": False}]

    est_video = config.get("video", False)
    articles  = []

    for entry in feed.entries[:MAX_ARTICLES]:
        try:
            titre_brut = nettoyer_html(entry.get("title", "Sans titre"))
            titre      = traduire_fr(titre_brut, config["lang"])
            resume_brut = nettoyer_html(
                entry.get("summary") or entry.get("description", "")
            )[:600]
            resume     = traduire_fr(resume_brut, config["lang"])
            if len(resume) > 320:
                resume = resume[:317] + "…"
            lien       = entry.get("link", "")
            date_str   = formater_date(entry)
            image_url  = None if est_video else extraire_image_url(entry)

            # Détection breaking news
            est_breaking = any(
                kw in titre_brut.lower() or kw in resume_brut.lower()
                for kw in BREAKING_KEYWORDS
            )

            prefixe = "🚨 *URGENT —* " if est_breaking else "📌 "

            if est_video:
                yt_id = ""
                if "youtube.com/watch?v=" in lien:
                    yt_id = lien.split("v=")[-1].split("&")[0]
                image_url = f"https://img.youtube.com/vi/{yt_id}/mqdefault.jpg" if yt_id else None
                texte = (
                    f"▶️ *{securiser_md(titre)}*\n"
                    f"{date_str}\n"
                    f"🔗 [Regarder sur YouTube]({lien})\n"
                )
            else:
                texte = (
                    f"{prefixe}*{securiser_md(titre)}*\n"
                    f"{date_str}\n"
                    f"{securiser_md(resume)}\n"
                    f"🔗 [Lire l'article complet]({lien})\n"
                )

            articles.append({
                "texte"      : texte,
                "image"      : image_url,
                "lien"       : lien,
                "titre_brut" : titre_brut,
                "est_breaking": est_breaking,
            })

        except Exception as exc:
            logger.warning("Entrée ignorée (%s) : %s", cle, exc)

    return articles or [{"texte": "⚠️ Aucun contenu exploitable.",
                          "image": None, "lien": "", "titre_brut": "", "est_breaking": False}]


# ══════════════════════════════════════════════════════
#  RECHERCHE MULTI-FLUX
# ══════════════════════════════════════════════════════
def rechercher_articles(mot_cle: str) -> list[dict]:
    """
    Cherche `mot_cle` dans tous les flux FEEDS.
    Retourne jusqu'à MAX_RECHERCHE résultats (dict similaire à recuperer_articles).
    """
    resultats = []
    mc = mot_cle.lower().strip()

    for cle, config in FEEDS.items():
        if config.get("video"):
            continue  # Pas de recherche dans les vidéos
        try:
            feed = feedparser.parse(config["url"])
            for entry in feed.entries:
                titre_brut  = nettoyer_html(entry.get("title", ""))
                resume_brut = nettoyer_html(entry.get("summary", ""))
                if mc in titre_brut.lower() or mc in resume_brut.lower():
                    titre     = traduire_fr(titre_brut, config["lang"])
                    resume    = traduire_fr(resume_brut[:400], config["lang"])
                    if len(resume) > 250:
                        resume = resume[:247] + "…"
                    lien      = entry.get("link", "")
                    date_str  = formater_date(entry)
                    image_url = extraire_image_url(entry)
                    resultats.append({
                        "texte": (
                            f"🔎 *{securiser_md(titre)}*\n"
                            f"{config['icon']} _{cle}_ — {date_str}\n"
                            f"{securiser_md(resume)}\n"
                            f"🔗 [Lire l'article]({lien})\n"
                        ),
                        "image"      : image_url,
                        "lien"       : lien,
                        "titre_brut" : titre_brut,
                        "est_breaking": False,
                    })
                    if len(resultats) >= MAX_RECHERCHE:
                        return resultats
        except Exception as exc:
            logger.debug("Recherche flux %s : %s", cle, exc)

    return resultats


# ══════════════════════════════════════════════════════
#  DÉTECTION BREAKING NEWS (tâche planifiée)
# ══════════════════════════════════════════════════════
async def verifier_breaking_news(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Parcourt les flux principaux, détecte les breaking news et alerte les abonnés."""
    abonnes = STATS.get("abonnes_notifs", [])
    if not abonnes:
        return

    deja_envoyes = set(STATS.get("breaking_envoyes", []))
    nouveaux     = []

    for cle in FEEDS_BREAKING:
        config = FEEDS.get(cle, {})
        try:
            feed = feedparser.parse(config["url"])
        except Exception:
            continue

        for entry in feed.entries[:5]:
            titre_brut = nettoyer_html(entry.get("title", ""))
            if titre_brut in deja_envoyes:
                continue
            est_breaking = any(kw in titre_brut.lower() for kw in BREAKING_KEYWORDS)
            if not est_breaking:
                continue

            titre    = traduire_fr(titre_brut, config.get("lang", "en"))
            resume_b = nettoyer_html(entry.get("summary", ""))[:300]
            resume   = traduire_fr(resume_b, config.get("lang", "en"))
            lien     = entry.get("link", "")
            image    = extraire_image_url(entry)

            alerte = (
                "🚨 *ACTUALITÉ IMPORTANTE*\n"
                f"{'▬' * 24}\n\n"
                f"*{securiser_md(titre)}*\n\n"
                f"{securiser_md(resume)}\n\n"
                f"🔗 [Lire l'article]({lien})\n\n"
                f"{'▬' * 24}\n"
                f"📡 Source : {config['icon']} _{cle}_\n"
                f"⏰ {datetime.now().strftime('%d/%m/%Y à %H:%M')}"
            )

            for uid in abonnes:
                try:
                    if image:
                        await context.bot.send_photo(
                            chat_id=uid,
                            photo=image,
                            caption=alerte,
                            parse_mode=ParseMode.MARKDOWN,
                        )
                    else:
                        await context.bot.send_message(
                            chat_id=uid,
                            text=alerte,
                            parse_mode=ParseMode.MARKDOWN,
                            disable_web_page_preview=False,
                        )
                except TelegramError as e:
                    logger.warning("Alerte non envoyée à %s : %s", uid, e)

            deja_envoyes.add(titre_brut)
            nouveaux.append(titre_brut)

    if nouveaux:
        # Limite la liste à 200 titres pour éviter la croissance infinie
        liste_envoyes = list(deja_envoyes)
        while len(liste_envoyes) > 200:
            liste_envoyes.pop(0)
        STATS["breaking_envoyes"] = liste_envoyes
        sauvegarder_stats(STATS)
        logger.info("Breaking news envoyé : %d alerte(s)", len(nouveaux))


# ══════════════════════════════════════════════════════
#  ENVOI D'ARTICLES (texte + image optionnelle)
# ══════════════════════════════════════════════════════
async def envoyer_articles(
    context_or_query,
    chat_id: int,
    articles: list[dict],
    en_tete: str,
    pied: str,
    clavier: InlineKeyboardMarkup,
    edit_query=None,
) -> None:
    """
    Envoie les articles avec image si disponible.
    - Si edit_query  → édite le message existant puis envoie les médias séparément
    - Sinon          → envoie direct au chat_id
    """
    # Extraction robuste de l'objet bot (depuis le contexte ou direct)
    if hasattr(context_or_query, "bot") and context_or_query.bot:
        bot = context_or_query.bot
    else:
        bot = context_or_query

    if not hasattr(bot, "send_message"):
        logger.error(f"Objet Bot invalide (type: {type(bot)})")
        return

    # 1. Message d'en-tête (édition ou nouveau message)
    texte_global = en_tete
    for art in articles:
        texte_global += "\n" + art["texte"] + "\n"
    texte_global += pied

    if edit_query:
        try:
            await edit_query.edit_message_text(
                text=texte_global,
                reply_markup=clavier,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True,
            )
        except BadRequest as e:
            if "message is not modified" not in str(e).lower():
                logger.warning("Edit échoué : %s", e)
    else:
        await bot.send_message(
            chat_id=chat_id,
            text=texte_global,
            reply_markup=clavier,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )

    # 2. Envoi des images (une par article qui en possède une)
    images_urls = [a["image"] for a in articles if a.get("image")]
    if not images_urls:
        return

    # Regroupe jusqu'à 10 images en un album (limite Telegram)
    media_group = []
    for url in images_urls[:5]:  # Max 5 images pour ne pas spammer
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                media_group.append(InputMediaPhoto(media=BytesIO(r.content)))
        except Exception as exc:
            logger.debug("Image non récupérée : %s", exc)

    if media_group:
        try:
            await bot.send_media_group(chat_id=chat_id, media=media_group)
        except TelegramError as e:
            logger.warning("Envoi album photos échoué : %s", e)


# ══════════════════════════════════════════════════════
#  CLAVIERS INLINE
# ══════════════════════════════════════════════════════
def clavier_principal() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🌍 Actualités",    callback_data="menu_pays"),
            InlineKeyboardButton("📚 Catégories",    callback_data="menu_cat"),
        ],
        [
            InlineKeyboardButton("🎬 Vidéos",        callback_data="menu_vid"),
            InlineKeyboardButton("🔍 Recherche",     callback_data="aide_recherche"),
        ],
        [
            InlineKeyboardButton("🚨 Breaking News", callback_data="menu_breaking"),
            InlineKeyboardButton("📊 Statistiques",  callback_data="stats"),
        ],
        [
            InlineKeyboardButton("🔔 Notifications", callback_data="notifs"),
            InlineKeyboardButton("ℹ️  À propos",      callback_data="about"),
        ],
    ])

def clavier_pays() -> InlineKeyboardMarkup:
    rangees = []
    for i in range(0, len(MENU_PAYS), 2):
        paire = MENU_PAYS[i:i+2]
        rangees.append([
            InlineKeyboardButton(f"{FEEDS[p]['icon']} {p}", callback_data=f"feed_{p}")
            for p in paire
        ])
    rangees.append([InlineKeyboardButton("⬅️ Retour", callback_data="accueil")])
    return InlineKeyboardMarkup(rangees)

def clavier_categories() -> InlineKeyboardMarkup:
    rangees = []
    for i in range(0, len(MENU_CATEGORIES), 2):
        paire = MENU_CATEGORIES[i:i+2]
        rangees.append([
            InlineKeyboardButton(f"{FEEDS[c]['icon']} {c}", callback_data=f"feed_{c}")
            for c in paire
        ])
    rangees.append([InlineKeyboardButton("⬅️ Retour", callback_data="accueil")])
    return InlineKeyboardMarkup(rangees)

def clavier_videos() -> InlineKeyboardMarkup:
    labels = {
        "Vidéos_DW_FR"  : "📺 DW Français",
        "Vidéos_Science": "🔭 Science étonnante",
        "Vidéos_Monde"  : "🌍 DW News",
    }
    rangees = [[InlineKeyboardButton(l, callback_data=f"feed_{k}")]
               for k, l in labels.items()]
    rangees.append([InlineKeyboardButton("⬅️ Retour", callback_data="accueil")])
    return InlineKeyboardMarkup(rangees)

def clavier_retour(cible: str = "accueil") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Retour au menu", callback_data=cible)]
    ])

def clavier_notifs(est_abonne: bool) -> InlineKeyboardMarkup:
    label = "🔕 Se désabonner" if est_abonne else "🔔 S'abonner aux alertes"
    action = "notif_off" if est_abonne else "notif_on"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(label, callback_data=action)],
        [InlineKeyboardButton("⬅️ Retour", callback_data="accueil")],
    ])

def clavier_breaking() -> InlineKeyboardMarkup:
    rangees = [
        [InlineKeyboardButton(
            f"{FEEDS[c]['icon']} {c}", callback_data=f"breaking_{c}"
        )]
        for c in FEEDS_BREAKING
    ]
    rangees.append([InlineKeyboardButton("⬅️ Retour", callback_data="accueil")])
    return InlineKeyboardMarkup(rangees)


# ══════════════════════════════════════════════════════
#  MESSAGES PRÉDÉFINIS
# ══════════════════════════════════════════════════════
MSG_ACCUEIL = (
    "👋 *Bonjour et bienvenue sur Nopi !*\n\n"
    "Je suis votre assistant d'information premium, développé avec ❤️ par *BenzoXDev*.\n\n"
    "📡 Je collecte en temps réel les dernières nouvelles depuis des sources mondiales fiables,\n"
    "les traduis automatiquement en français et les enrichis pour vous.\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "🗂 *Options disponibles :*\n"
    "🌍 *Actualités* — Par pays (France, USA, Russie, Monde…)\n"
    "📚 *Catégories* — Science, Techno, IA, Crypto, Sport…\n"
    "🎬 *Vidéos* — Chaînes YouTube d'info en français\n"
    "🔍 *Recherche* — Chercher par mot-clé dans tous les flux\n"
    "🚨 *Breaking News* — Actualités urgentes par pays\n"
    "📊 *Statistiques* — Utilisation du bot\n"
    "🔔 *Notifications* — Alertes breaking news en temps réel\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "👇 *Choisissez une option :*"
)

MSG_AIDE = (
    "🆘 *Guide d'utilisation — Nopi Bot V3*\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "📌 *Commandes principales :*\n"
    "/start         — Menu d'accueil\n"
    "/aide          — Ce message d'aide\n"
    "/pays          — Actualités par pays\n"
    "/cat           — Actualités par catégorie\n"
    "/vid           — Vidéos YouTube\n"
    "/breaking      — Actualités urgentes\n"
    "/recherche mot — Chercher 'mot' dans tous les flux\n"
    "/stats         — Statistiques du bot\n"
    "/notifs        — Gérer les alertes\n"
    "/about         — À propos\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "🔍 *Exemple de recherche :*\n"
    "`/recherche intelligence artificielle`\n"
    "`/recherche ukraine`\n"
    "`/recherche bitcoin`\n\n"
    "💡 La recherche parcourt *tous* les flux RSS disponibles.\n\n"
    f"🛠 Support : {BOT_AUTHOR}"
)

MSG_ABOUT = (
    "ℹ️ *À propos de Nopi*\n\n"
    f"🤖 Version : *{BOT_VERSION}*\n"
    "🛠 Développé par : *BenzoXDev*\n\n"
    "🌐 *Sources d'information :*\n"
    "Le Monde · BBC · NYT · RT · ScienceDaily\n"
    "NASA · OMS · TechCrunch · The Guardian\n"
    "MarketWatch · Sky Sports · CoinTelegraph\n\n"
    "⚙️ *Technologies :*\n"
    "Python · python-telegram-bot · feedparser\n"
    "deep-translator · requests\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "💬 *Contact & Support :*\n"
    f"Pour toute question ou suggestion : {BOT_AUTHOR}\n\n"
    "🙏 Merci d'utiliser Nopi — votre fenêtre sur le monde 🌏"
)


# ══════════════════════════════════════════════════════
#  COMMANDES TELEGRAM
# ══════════════════════════════════════════════════════
def enregistrer_utilisateur(user_id: int, categorie: str = None) -> None:
    """Met à jour les statistiques d'utilisation."""
    if user_id not in STATS["utilisateurs_uniques"]:
        STATS["utilisateurs_uniques"].append(user_id)
    STATS["total_requetes"] += 1
    if categorie:
        STATS["requetes_par_cat"][categorie] = \
            STATS["requetes_par_cat"].get(categorie, 0) + 1
    sauvegarder_stats(STATS)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    enregistrer_utilisateur(uid)
    if update.message:
        await update.message.reply_text(
            MSG_ACCUEIL,
            reply_markup=clavier_principal(),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )

async def cmd_aide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text(
            MSG_AIDE,
            reply_markup=clavier_retour(),
            parse_mode=ParseMode.MARKDOWN,
        )

async def cmd_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text(
            MSG_ABOUT,
            reply_markup=clavier_retour(),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )

async def cmd_pays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text(
            "🌍 *Choisissez un pays :*",
            reply_markup=clavier_pays(),
            parse_mode=ParseMode.MARKDOWN,
        )

async def cmd_cat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text(
            "📚 *Choisissez une catégorie :*",
            reply_markup=clavier_categories(),
            parse_mode=ParseMode.MARKDOWN,
        )

async def cmd_vid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text(
            "🎬 *Choisissez une chaîne vidéo :*",
            reply_markup=clavier_videos(),
            parse_mode=ParseMode.MARKDOWN,
        )

async def cmd_breaking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text(
            "🚨 *Breaking News — Choisissez une source :*\n\n"
            "Je vais filtrer les actualités contenant des mots-clés d'urgence.",
            reply_markup=clavier_breaking(),
            parse_mode=ParseMode.MARKDOWN,
        )

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les statistiques d'utilisation du bot."""
    uid = update.effective_user.id
    enregistrer_utilisateur(uid)

    nb_users = len(STATS["utilisateurs_uniques"])
    nb_req   = STATS["total_requetes"]
    nb_rech  = STATS.get("recherches", 0)
    nb_ab    = len(STATS.get("abonnes_notifs", []))
    nb_break = len(STATS.get("breaking_envoyes", []))

    # Top 5 catégories
    cats = sorted(
        STATS["requetes_par_cat"].items(), key=lambda x: x[1], reverse=True
    )[:5]
    top_cats = "\n".join(
        f"  {i+1}. {FEEDS.get(c, {}).get('icon', '📌')} *{c}* — {n} fois"
        for i, (c, n) in enumerate(cats)
    ) or "  _Aucune donnée_"

    # Uptime
    try:
        demarrage = datetime.fromisoformat(STATS["demarrage"])
        uptime    = datetime.now() - demarrage
        jours     = uptime.days
        heures    = uptime.seconds // 3600
        uptime_str = f"{jours}j {heures}h"
    except Exception:
        uptime_str = "N/A"

    texte = (
        "📊 *Statistiques — Nopi Bot*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Utilisateurs uniques  : *{nb_users}*\n"
        f"📨 Total requêtes        : *{nb_req}*\n"
        f"🔍 Recherches effectuées : *{nb_rech}*\n"
        f"🔔 Abonnés notifications : *{nb_ab}*\n"
        f"🚨 Breaking news détectés: *{nb_break}*\n"
        f"⏱ Uptime                : *{uptime_str}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏆 *Top 5 catégories les plus consultées :*\n"
        f"{top_cats}\n\n"
        f"🕐 Données depuis : _{STATS['demarrage'][:10]}_"
    )
    if update.message:
        await update.message.reply_text(
            texte,
            reply_markup=clavier_retour(),
            parse_mode=ParseMode.MARKDOWN,
        )

async def cmd_notifs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    est_abonne = uid in STATS.get("abonnes_notifs", [])
    texte = (
        "🔔 *Gestion des notifications*\n\n"
        f"Statut actuel : {'✅ *Abonné*' if est_abonne else '❌ *Non abonné*'}\n\n"
        "En vous abonnant, vous recevrez automatiquement une alerte\n"
        "dès qu'une actualité importante est détectée dans nos flux\n"
        f"_(vérification toutes les {BREAKING_INTERVAL // 60} minutes)_."
    )
    if update.message:
        await update.message.reply_text(
            texte,
            reply_markup=clavier_notifs(est_abonne),
            parse_mode=ParseMode.MARKDOWN,
        )


async def cmd_recherche(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Commande /recherche <mot-clé>
    Exemple : /recherche intelligence artificielle
    """
    uid = update.effective_user.id
    enregistrer_utilisateur(uid, "Recherche")
    STATS["recherches"] = STATS.get("recherches", 0) + 1
    sauvegarder_stats(STATS)

    if not context.args:
        await update.message.reply_text(
            "🔍 *Comment utiliser la recherche :*\n\n"
            "Tapez `/recherche` suivi de votre mot-clé.\n\n"
            "📝 *Exemples :*\n"
            "`/recherche intelligence artificielle`\n"
            "`/recherche ukraine`\n"
            "`/recherche bitcoin`\n"
            "`/recherche nasa mars`\n\n"
            "💡 La recherche parcourt *tous* les flux RSS disponibles.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    mot_cle = " ".join(context.args)

    # Message d'attente
    msg_attente = await update.message.reply_text(
        f"🔍 Recherche de *{securiser_md(mot_cle)}* dans tous les flux…\n"
        "_(Cela peut prendre quelques secondes)_",
        parse_mode=ParseMode.MARKDOWN,
    )

    resultats = rechercher_articles(mot_cle)

    if not resultats:
        await msg_attente.edit_text(
            f"😔 Aucun résultat pour *{securiser_md(mot_cle)}*.\n\n"
            "💡 Essayez un autre mot-clé ou en anglais.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=clavier_retour(),
        )
        return

    sep = "▬" * 22
    en_tete = (
        f"🔍 *RÉSULTATS — \"{securiser_md(mot_cle)}\"*\n"
        f"{sep}\n"
        f"_{len(resultats)} article(s) trouvé(s)_\n\n"
    )
    pied = (
        f"\n{sep}\n"
        f"🕐 {datetime.now().strftime('%d/%m/%Y à %H:%M')}\n"
        f"💬 [{BOT_AUTHOR}](https://t.me/benzoXdev) | *Nopi V3* 🌟"
    )

    # On édite le message d'attente avec le résumé textuel
    texte_global = en_tete
    for art in resultats:
        texte_global += art["texte"] + "\n"
    texte_global += pied

    try:
        await msg_attente.edit_text(
            texte_global,
            reply_markup=clavier_retour(),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )
    except BadRequest as e:
        if "message is not modified" not in str(e).lower():
            logger.warning("Édition résultat recherche : %s", e)

    # Envoi des images trouvées
    images = [a["image"] for a in resultats if a.get("image")]
    if images:
        media_group = []
        for url in images[:4]:
            try:
                r = requests.get(url, timeout=5)
                if r.status_code == 200:
                    media_group.append(InputMediaPhoto(media=BytesIO(r.content)))
            except Exception:
                pass
        if media_group:
            try:
                await update.message.reply_media_group(media=media_group)
            except TelegramError as e:
                logger.warning("Album photos recherche : %s", e)


# ══════════════════════════════════════════════════════
#  HANDLER BOUTONS INLINE
# ══════════════════════════════════════════════════════
async def handler_bouton(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data  = query.data
    uid   = query.from_user.id

    # ── Aide recherche ────────────────────────────────
    if data == "aide_recherche":
        await _edit(query,
            "🔍 *Commande Recherche*\n\n"
            "Tapez directement dans le chat :\n"
            "`/recherche <mot-clé>`\n\n"
            "📝 *Exemples :*\n"
            "`/recherche Chine`\n"
            "`/recherche ChatGPT`\n"
            "`/recherche séisme`\n\n"
            "La recherche parcourt *tous* les flux RSS disponibles.",
            clavier_retour()
        )
        return

    # ── Navigation menus ──────────────────────────────
    nav_map = {
        "accueil"  : (MSG_ACCUEIL, clavier_principal()),
        "menu_pays": ("🌍 *Sélectionnez un pays :*", clavier_pays()),
        "menu_cat" : ("📚 *Sélectionnez une catégorie :*", clavier_categories()),
        "menu_vid" : ("🎬 *Sélectionnez une chaîne vidéo :*", clavier_videos()),
        "about"    : (MSG_ABOUT, clavier_retour()),
        "menu_breaking": (
            "🚨 *Breaking News — Choisissez une source :*\n\n"
            "Filtre les actualités contenant des mots-clés d'urgence.",
            clavier_breaking()
        ),
    }
    if data in nav_map:
        txt, kb = nav_map[data]
        await _edit(query, txt, kb)
        return

    # ── Statistiques ──────────────────────────────────
    if data == "stats":
        enregistrer_utilisateur(uid)
        nb_users = len(STATS["utilisateurs_uniques"])
        nb_req   = STATS["total_requetes"]
        nb_rech  = STATS.get("recherches", 0)
        nb_ab    = len(STATS.get("abonnes_notifs", []))
        cats = sorted(STATS["requetes_par_cat"].items(),
                      key=lambda x: x[1], reverse=True)[:5]
        top  = "\n".join(
            f"  {i+1}. {FEEDS.get(c, {}).get('icon', '📌')} *{c}* — {n} fois"
            for i, (c, n) in enumerate(cats)
        ) or "  _Aucune donnée_"
        try:
            uptime = datetime.now() - datetime.fromisoformat(STATS["demarrage"])
            uptime_str = f"{uptime.days}j {uptime.seconds//3600}h"
        except Exception:
            uptime_str = "N/A"
        texte = (
            "📊 *Statistiques — Nopi Bot*\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 Utilisateurs uniques   : *{nb_users}*\n"
            f"📨 Total requêtes         : *{nb_req}*\n"
            f"🔍 Recherches effectuées  : *{nb_rech}*\n"
            f"🔔 Abonnés notifications  : *{nb_ab}*\n"
            f"🚨 Breaking détectés      : *{len(STATS.get('breaking_envoyes',[]))}*\n"
            f"⏱ Uptime                 : *{uptime_str}*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🏆 *Top catégories :*\n{top}"
        )
        await _edit(query, texte, clavier_retour())
        return

    # ── Notifications ─────────────────────────────────
    if data == "notifs":
        est_ab = uid in STATS.get("abonnes_notifs", [])
        texte = (
            "🔔 *Gestion des notifications*\n\n"
            f"Statut : {'✅ *Abonné*' if est_ab else '❌ *Non abonné*'}\n\n"
            "Recevez une alerte automatique dès qu'une actualité\n"
            f"importante est détectée _(toutes les {BREAKING_INTERVAL//60} min)_."
        )
        await _edit(query, texte, clavier_notifs(est_ab))
        return

    if data == "notif_on":
        abonnes = STATS.setdefault("abonnes_notifs", [])
        if uid not in abonnes:
            abonnes.append(uid)
            sauvegarder_stats(STATS)
        await _edit(query,
            "✅ *Notifications activées !*\n\n"
            "Vous recevrez une alerte dès qu'une actualité importante\n"
            f"est détectée _(vérification toutes les {BREAKING_INTERVAL//60} min)_.",
            clavier_retour()
        )
        return

    if data == "notif_off":
        abonnes = STATS.get("abonnes_notifs", [])
        if uid in abonnes:
            abonnes.remove(uid)
            sauvegarder_stats(STATS)
        await _edit(query,
            "🔕 *Notifications désactivées.*\n\n"
            "Vous ne recevrez plus d'alertes automatiques.\n"
            "Vous pouvez vous réabonner à tout moment.",
            clavier_retour()
        )
        return

    # ── Breaking News par flux ────────────────────────
    if data.startswith("breaking_"):
        cle = data[9:]
        config = FEEDS.get(cle)
        if not config:
            await query.answer("❌ Source introuvable.", show_alert=True)
            return

        await _edit(query,
            f"🚨 Recherche des actualités urgentes pour *{config['icon']} {cle}*…",
            None
        )

        articles_raw = recuperer_articles(cle)
        breaking = [a for a in articles_raw if a["est_breaking"]]

        if not breaking:
            await _edit(query,
                f"✅ Aucune actualité urgente détectée pour *{cle}* en ce moment.\n\n"
                "Nos algorithmes surveillent en permanence les mots-clés d'alerte.",
                clavier_retour("menu_breaking")
            )
            return

        sep = "▬" * 22
        en_tete = (
            f"🚨 *BREAKING NEWS — {cle.upper()}*\n"
            f"{config['icon']} _{config['desc']}_\n"
            f"{sep}\n\n"
        )
        pied = (
            f"\n{sep}\n"
            f"🕐 {datetime.now().strftime('%d/%m/%Y à %H:%M')}\n"
            f"💬 [{BOT_AUTHOR}](https://t.me/benzoXdev) | *Nopi V3* 🌟"
        )

        enregistrer_utilisateur(uid, f"Breaking_{cle}")
        chat_id = query.message.chat_id
        await envoyer_articles(
            context, chat_id, breaking, en_tete, pied,
            clavier_retour("menu_breaking"), edit_query=query
        )
        return

    # ── Chargement flux RSS standard ─────────────────
    if data.startswith("feed_"):
        cle = data[5:]
        config = FEEDS.get(cle)
        if not config:
            await query.answer("❌ Source introuvable.", show_alert=True)
            return

        await _edit(query,
            f"⏳ Chargement de *{config['icon']} {cle}*…\n"
            "_(Traduction en cours si nécessaire)_",
            None
        )

        articles_raw = recuperer_articles(cle)
        enregistrer_utilisateur(uid, cle)

        sep = "▬" * 22
        en_tete = (
            f"{config['icon']} *{cle.upper().replace('_', ' ')}*\n"
            f"📡 _{config['desc']}_\n{sep}\n\n"
        )
        pied = (
            f"\n{sep}\n"
            f"🕐 {datetime.now().strftime('%d/%m/%Y à %H:%M')}\n"
            f"💬 [{BOT_AUTHOR}](https://t.me/benzoXdev) | *Nopi V3* 🌟"
        )

        retour = (
            "menu_pays" if cle in MENU_PAYS
            else "menu_cat" if cle in MENU_CATEGORIES
            else "menu_vid"
        )
        chat_id = query.message.chat_id
        await envoyer_articles(
            context, chat_id, articles_raw, en_tete, pied,
            clavier_retour(retour), edit_query=query
        )
        return

    await query.answer("⚠️ Action inconnue.", show_alert=True)


async def _edit(query, texte: str, clavier) -> None:
    """Édite le message inline avec gestion d'erreur."""
    kwargs = {
        "text"                    : texte,
        "parse_mode"              : ParseMode.MARKDOWN,
        "disable_web_page_preview": True,
    }
    if clavier:
        kwargs["reply_markup"] = clavier
    try:
        await query.edit_message_text(**kwargs)
    except BadRequest as e:
        if "message is not modified" not in str(e).lower():
            logger.warning("_edit BadRequest : %s", e)


# ══════════════════════════════════════════════════════
#  HANDLER TEXTE (messages non-commandes)
# ══════════════════════════════════════════════════════
async def handler_texte(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Si l'utilisateur envoie un texte sans commande, propose la recherche."""
    texte = update.message.text.strip()
    if len(texte) < 2:
        return
    await update.message.reply_text(
        f"🔍 Voulez-vous rechercher *{securiser_md(texte)}* dans tous les flux ?\n\n"
        f"Tapez : `/recherche {securiser_md(texte)}`",
        parse_mode=ParseMode.MARKDOWN,
    )


# ══════════════════════════════════════════════════════
#  CONFIGURATION COMMANDES TELEGRAM (menu /)
# ══════════════════════════════════════════════════════
async def definir_commandes(application) -> None:
    cmds = [
        BotCommand("start",     "🏠 Menu principal"),
        BotCommand("aide",      "🆘 Aide et commandes"),
        BotCommand("pays",      "🌍 Actualités par pays"),
        BotCommand("cat",       "📚 Actualités par catégorie"),
        BotCommand("vid",       "🎬 Vidéos YouTube"),
        BotCommand("breaking",  "🚨 Actualités urgentes"),
        BotCommand("recherche", "🔍 Rechercher un mot-clé"),
        BotCommand("stats",     "📊 Statistiques du bot"),
        BotCommand("notifs",    "🔔 Gérer les alertes"),
        BotCommand("about",     "ℹ️  À propos de Nopi"),
    ]
    await application.bot.set_my_commands(cmds)
    logger.info("✅ Commandes Telegram enregistrées.")


# ══════════════════════════════════════════════════════
#  POINT D'ENTRÉE
# ══════════════════════════════════════════════════════
def main() -> None:
    print("╔═══════════════════════════════════════════════╗")
    print("║    NOPI BOT V3 Ultra — Démarrage en cours…    ║")
    print("╚═══════════════════════════════════════════════╝\n")

    if TOKEN == "VOTRE_TOKEN_ICI":
        print("⚠️  TOKEN manquant ! Remplacez VOTRE_TOKEN_ICI dans le fichier.\n")
    if not TRANSLATION_OK:
        print("⚠️  deep-translator absent → traductions désactivées.")
        print("   Installez : pip install deep-translator\n")

    application = (
        ApplicationBuilder()
        .token(TOKEN)
        .post_init(definir_commandes)
        .build()
    )

    # ── Planificateur breaking news ───────────────────
    application.job_queue.run_repeating(
        verifier_breaking_news,
        interval=BREAKING_INTERVAL,
        first=60,   # Premier check 60s après démarrage
        name="breaking_news_watcher",
    )

    # ── Commandes ─────────────────────────────────────
    for cmd, fn in [
        ("start",    cmd_start),
        ("aide",     cmd_aide),
        ("help",     cmd_aide),
        ("about",    cmd_about),
        ("pays",     cmd_pays),
        ("cat",      cmd_cat),
        ("vid",      cmd_vid),
        ("breaking", cmd_breaking),
        ("stats",    cmd_stats),
        ("notifs",   cmd_notifs),
        ("recherche",cmd_recherche),
    ]:
        application.add_handler(CommandHandler(cmd, fn))

    # ── Boutons inline ────────────────────────────────
    application.add_handler(CallbackQueryHandler(handler_bouton))

    # ── Messages texte libres ─────────────────────────
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handler_texte
    ))

    print("✅ Bot opérationnel ! En écoute…\n")
    logger.info("Nopi Bot v%s démarré.", BOT_VERSION)
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()