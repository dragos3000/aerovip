"""Home airfield reference data: editable in Settings, shown on the dashboard.

Each field is stored as a Setting (key/value). Until an admin saves, the default
(the values supplied for the home airfield) is shown, so nothing is blank.
"""
from app.models import Setting

# (setting_key, label_translation_key, default_value, multiline)
AIRFIELD_FIELDS = [
    ('af_arp_coords', 'af.arp_coords', "44°55'25\"N 025°57'48\"E (centrul pistei)", False),
    ('af_elevation', 'af.elevation', '573ft (175m)', False),
    ('af_ref_temp', 'af.ref_temp', '25°C (77°F) / -5°C (23°F)', False),
    ('af_freq', 'af.freq', '131.455', False),
    ('af_traffic', 'af.traffic', 'VFR', False),
    ('af_horizontal', 'af.horizontal',
     "Cerc cu raza de 5NM (10km) centrat pe coordonatele 44°55'00\"N 025°58'00\"E", True),
    ('af_vertical', 'af.vertical', 'GND - 4000ft (1220m) QNH', False),
    ('af_airspace', 'af.airspace', 'Clasa G', False),
    ('af_rec_altitude', 'af.rec_altitude',
     "Tur de pistă sud 07/25: 1400ft (427m) QNH\n"
     "Tur de pistă nord 09/27: 1200ft (366m) QNH\n"
     "Zone de lucru: minim 2000ft (607m) QNH", True),
    ('af_local_proc', 'af.local_proc', 'Nu mai mult de 5 aeronave în turul de pistă sud', True),
]


# Separate Google My Maps for each language (different maps, not just a language param).
AIRFIELD_MAP_DEFAULT = ('https://www.google.com/maps/d/u/2/embed'
                        '?mid=1sEpcUBdC6w5XrZe0Ylbj7NSRYN5fxGg&ehbc=2E312F&z=12')
AIRFIELD_MAP_DEFAULT_EN = ('https://www.google.com/maps/d/u/2/embed'
                           '?mid=16LrxAFkeF4YhxS8pmVhjHVy0Cj6c080&ehbc=2E312F&z=12')


def get_airfield_map_url(lang='ro'):
    if lang == 'en':
        return Setting.get('airfield_map_url_en', AIRFIELD_MAP_DEFAULT_EN)
    return Setting.get('airfield_map_url', AIRFIELD_MAP_DEFAULT)


def get_airfield_info():
    """List of fields with current (or default) values, for display and the settings form."""
    return [
        {
            'key': key,
            'label_key': label_key,
            'value': Setting.get(key, default),
            'multiline': multiline,
        }
        for key, label_key, default, multiline in AIRFIELD_FIELDS
    ]


def save_airfield_info(form_data):
    """Persist submitted airfield fields (form_data is request.form)."""
    for key, _label, default, _ml in AIRFIELD_FIELDS:
        Setting.set(key, (form_data.get(key) or '').strip(), 'Home airfield information')
    if 'airfield_map_url' in form_data:
        Setting.set('airfield_map_url', (form_data.get('airfield_map_url') or '').strip(),
                    'Home airfield map embed URL (RO)')
    if 'airfield_map_url_en' in form_data:
        Setting.set('airfield_map_url_en', (form_data.get('airfield_map_url_en') or '').strip(),
                    'Home airfield map embed URL (EN)')
