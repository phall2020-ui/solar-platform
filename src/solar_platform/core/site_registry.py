"""
site_registry.py — Single source of truth for platform site ID / name → canonical
Asset Register name mapping.

Two lookup tables:
  SITE_ID_MAP    — (normalised_platform, site_id) → asset_register_name
  SITE_NAME_MAP  — normalised_monitoring_name     → asset_register_name

Resolution order:
  1. SITE_ID_MAP lookup by (platform, site_id)
  2. SITE_NAME_MAP lookup by normalised site_name
  3. Caller falls back to raw site_name

Sources:
  solar-platform/config/site_locations.json
  solar-platform/src/solar_platform/services/copilot/models.py
    DEFAULT_DATA_SOURCE_MATCH_UPDATES  (Asset Register name → canonical name)
    DEFAULT_CONFIRMED_SOURCE_REGISTRY  (canonical name → platform + site_id)
"""

# ---------------------------------------------------------------------------
# (normalised_platform, site_id) → Asset Register name
# ---------------------------------------------------------------------------
SITE_ID_MAP: dict[tuple[str, str], str] = {

    # SolarEdge
    ("solaredge", "4667531"):  "Park Hall",
    ("solaredge", "3933004"):  "Uniroyal Global",
    ("solaredge", "2798969"):  "Shawton Engineering",
    ("solaredge", "4519032"):  "Panorama Kitchens",
    ("solaredge", "3829329"):  "WALC Adult Learning Centre",
    ("solaredge", "3490228"):  "Dunham Forest Golf Club",
    ("solaredge", "2733539"):  "Burnley College",
    ("solaredge", "4338522"):  "Bannatyne's Wildmoor",
    ("solaredge", "3823337"):  "WALC Pagefield",
    ("solaredge", "3888537"):  "WALC Leigh College",
    ("solaredge", "2626861"):  "Valley Hydraulics",
    ("solaredge", "3656221"):  "Swift Dental Group",
    ("solaredge", "2688590"):  "I&N Fabrications",
    ("solaredge", "4283465"):  "Bannatyne's Weybridge",
    ("solaredge", "4319038"):  "Bannatyne's Norwich",
    ("solaredge", "4307544"):  "Bannatyne's Darlington",
    ("solaredge", "4361798"):  "Bannatyne's Cookridge Hall",
    ("solaredge", "4320553"):  "Bannatyne's Colchester Kingsford Park",
    ("solaredge", "4309872"):  "Bannatyne's Bury St Edmunds",
    ("solaredge", "4284090"):  "Bannatyne's Braintree",
    ("solaredge", "4756575"):  "Casepak Sunningdale",
    ("solaredge", "4466155"):  "Blachford",
    ("solaredge", "4209270"):  "Princes / Knowles",
    ("solaredge", "4625192"):  "Inktech",

    # Solis (station IDs from SolisCloud API)
    ("solis", "1298491919450070492"):  "Finlay Beverages",
    ("solis", "1298491919449993293"):  "Sofina Haverhill",
    ("solis", "1298491919449898612"):  "Smithy's Mushrooms (Ph1)",  # shared station: PH1+2
    ("solis", "1298491919449855581"):  "Parfetts Birmingham",
    ("solis", "1298491919449813631"):  "Faltec",
    ("solis", "1298491919449006183"):  "Hibernian Training Ground",
    ("solis", "1298491919449005781"):  "Hibernian Stadium",
    ("solis", "1298491919448677612"):  "Besblock",

    # Juggle (plantUID / juggle_uid)
    ("juggle", "ERS:00001"):   "BAE Fylde",
    ("juggle", "AMP:00001"):   "Cromwell Tools",
    ("juggle", "AMP:00002"):   "Hibernian Stadium",
    ("juggle", "AMP:00003"):   "Hibernian Training Ground",
    ("juggle", "AMP:00019"):   "City Football Group Phase 1",
    ("juggle", "AMP:00020"):   "Sheldons Bakery",
    ("juggle", "AMP:00024"):   "Blachford",
    ("juggle", "AMP:00025"):   "Merry Hill",
    ("juggle", "AMP:00026"):   "Parfetts Birmingham",
    ("juggle", "AMP:00027"):   "Metro Centre",
    ("juggle", "AMP:00028"):   "Smithy's Mushrooms (Ph1)",
    ("juggle", "AMP:00029"):   "Sofina Haverhill",
    ("juggle", "AMP:00031"):   "Finlay Beverages",
    ("juggle", "AMP:00032"):   "Wienerberger Floplast",
    ("juggle", "AMP:00033"):   "Smithy's Mushrooms (Ph2)",
    ("juggle", "AMP:00035"):   "Orkla - Barking",
    ("juggle", "AMP:00041"):   "Besblock",
    ("juggle", "HARP:00024"):  "Casepak Sunningdale",
    ("juggle", "HARP:00025"):  "Casepak Warren Park Way",
    ("juggle", "HARP:00026"):  "Casepak Warren Park Way",
    ("juggle", "ASTR:00001"):  "DLG - Stevenage",
    ("juggle", "ASTR:00002"):  "DLG - Dundee",
    ("juggle", "ASTR:00003"):  "DLG - Hamilton",
    ("juggle", "CUSP:00034"):  "DLG - Purley",
}

# ---------------------------------------------------------------------------
# normalised monitoring site name → Asset Register name
# Normalised = lower-case, leading/trailing whitespace stripped.
# ---------------------------------------------------------------------------
SITE_NAME_MAP: dict[str, str] = {
    # SolarEdge PPA names
    "ppa park hall":                                    "Park Hall",
    "ppa uniroyal global":                              "Uniroyal Global",
    "ppa shawton engineering ltd":                      "Shawton Engineering",
    "ppa princes tuna":                                 "Princes / Knowles",
    "ppa panorama kitchens":                            "Panorama Kitchens",
    "ppa walc adult learning centre":                   "WALC Adult Learning Centre",
    "ppa dunham forest golf club":                      "Dunham Forest Golf Club",
    "ppa burnley college":                              "Burnley College",
    "ppa bannatynes wildmoor":                          "Bannatyne's Wildmoor",
    "ppa walc pagefield":                               "WALC Pagefield",
    "ppa walc leigh college":                           "WALC Leigh College",
    "ppa valley hydraulics":                            "Valley Hydraulics",
    "ppa swift dental group":                           "Swift Dental Group",
    "ppa ink tech":                                     "Inktech",
    "ppa i&n fabrications ltd":                         "I&N Fabrications",
    "ppa bannatynes weybridge":                         "Bannatyne's Weybridge",
    "ppa bannatynes norwich":                           "Bannatyne's Norwich",
    "ppa bannatynes darlington head office":            "Bannatyne's Darlington",
    "ppa bannatynes cookridge hall":                    "Bannatyne's Cookridge Hall",
    "ppa bannatynes colchester kingsford park":         "Bannatyne's Colchester Kingsford Park",
    "ppa bannatynes bury st edmunds":                   "Bannatyne's Bury St Edmunds",
    "ppa bannatynes braintree":                         "Bannatyne's Braintree",
    "ppa bannatynes darlington":                        "Bannatyne's Darlington",

    # SolarEdge non-PPA names
    "blachford uk":                                     "Blachford",
    "casepak sunningdale - mpan 159":                   "Casepak Sunningdale",
    "casepak sunningdale":                              "Casepak Sunningdale",
    "casepak (sunningdale road)":                       "Casepak Sunningdale",
    "casepak sunningdale road":                         "Casepak Sunningdale",

    # Merry Hill — three SolarEdge MPANs all map to the same Asset Register row
    "merryhill white mpan00000000":                     "Merry Hill",
    "merryhill red mpan0005":                           "Merry Hill",
    "merryhill blue mpan 00003":                        "Merry Hill",
    "merry hill":                                       "Merry Hill",
    "merry hill shopping centre":                       "Merry Hill",

    # Solis names (as returned by SolisCloud API — often abbreviated)
    "finlay beverages":                                 "Finlay Beverages",
    "haverhill":                                        "Sofina Haverhill",
    "sofina foods":                                     "Sofina Haverhill",
    "sofina haverhill":                                 "Sofina Haverhill",
    "smithy mushroom":                                  "Smithy's Mushrooms (Ph1)",
    "smithy's mushrooms ph1":                           "Smithy's Mushrooms (Ph1)",
    "smithy's mushrooms ph2":                           "Smithy's Mushrooms (Ph2)",
    "smithy's mushrooms (ph1)":                         "Smithy's Mushrooms (Ph1)",
    "smithy's mushrooms (ph2)":                         "Smithy's Mushrooms (Ph2)",
    "parfetts birmingham":                              "Parfetts Birmingham",
    "faltec europe ltd":                                "Faltec",
    "hibernian training ground":                        "Hibernian Training Ground",
    "hibernian stadium":                                "Hibernian Stadium",
    "besblock":                                         "Besblock",

    # Juggle canonical names → Asset Register names
    "besblock ltd":                                     "Besblock",
    "casepak warren park way mpan 853":                 "Casepak Warren Park Way",
    "casepak warren park way mpan 397":                 "Casepak Warren Park Way",
    "casepak warren park way":                          "Casepak Warren Park Way",
    "david lloyd - stevenage":                          "DLG - Stevenage",
    "david lloyd stevenage":                            "DLG - Stevenage",
    "david lloyd dundee":                               "DLG - Dundee",
    "david lloyd hamilton":                             "DLG - Hamilton",
    "david lloyd purley":                               "DLG - Purley",
    "newfold farm":                                     "BAE Fylde",
    "cromwell tools":                                   "Cromwell Tools",
    "man city fc training ground":                      "City Football Group Phase 1",
    "city football group phase 1":                      "City Football Group Phase 1",
    "sheldons bakery":                                  "Sheldons Bakery",
    "metrocentre":                                      "Metro Centre",
    "metro centre":                                     "Metro Centre",
    "floplast":                                         "Wienerberger Floplast",
    "wienerberger floplast":                            "Wienerberger Floplast",
    "orkla - barking":                                  "Orkla - Barking",
    "nic barking":                                      "Orkla - Barking",
}


def resolve(platform: str, site_id: str, site_name: str) -> str | None:
    """
    Return the canonical Asset Register name for a monitoring site, or None
    if the site cannot be matched (caller should use the raw site_name as
    a fallback and create a new Notion row).

    Args:
        platform:  Platform name as returned by the monitoring client
                   (e.g. "SolarEdge", "Solis", "Juggle").
        site_id:   Platform-specific site identifier string.
        site_name: Human-readable site name from the platform.
    """
    norm_platform = platform.lower().replace(" ", "")
    norm_platform = {
        "fusionsolar": "huawei",
        "soliscloud":  "solis",
        "isolarcloud": "sungrow",
    }.get(norm_platform, norm_platform)

    key = (norm_platform, str(site_id).strip())
    if key in SITE_ID_MAP:
        return SITE_ID_MAP[key]

    norm_name = site_name.lower().strip()
    if norm_name in SITE_NAME_MAP:
        return SITE_NAME_MAP[norm_name]

    return None
