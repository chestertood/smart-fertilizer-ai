"""Minimal English/Thai UI string table.

Scope: navigation, section headers, and primary buttons — the
highest-visibility text. Field labels and dynamic status/error messages are
left as-is for now; translating every string in the app is a much bigger job
than this pass covers.
"""

EN = "en"
TH = "th"

LANGUAGES = [EN, TH]

_STRINGS = {
    "nav.dashboard":  {EN: "Dashboard", TH: "แดชบอร์ด"},
    "nav.parameters": {EN: "Parameters", TH: "พารามิเตอร์"},
    "nav.history":    {EN: "History", TH: "ประวัติ"},
    "nav.settings":   {EN: "Settings", TH: "ตั้งค่า"},

    "dashboard.title":    {EN: "Sensor Dashboard", TH: "แดชบอร์ดเซนเซอร์"},
    "dashboard.subtitle": {EN: "Real-time monitoring", TH: "ติดตามผลแบบเรียลไทม์"},
    "dashboard.online":   {EN: "Online", TH: "ออนไลน์"},
    "dashboard.offline":  {EN: "Offline", TH: "ออฟไลน์"},

    "parameters.title": {EN: "Parameters", TH: "พารามิเตอร์"},
    "parameters.section.setpoints":    {EN: "Setpoints", TH: "ค่าตั้งต้น"},
    "parameters.section.growth":       {EN: "Growth stages", TH: "ระยะการเติบโต"},
    "parameters.section.rules":        {EN: "Auto-dose rules", TH: "กฎการจ่ายอัตโนมัติ"},
    "parameters.section.dosing":       {EN: "Manual dosing", TH: "จ่ายด้วยมือ"},
    "parameters.section.calibration":  {EN: "Calibration", TH: "ปรับเทียบ"},
    "parameters.save":     {EN: "Save", TH: "บันทึก"},
    "parameters.reset":    {EN: "Reset", TH: "รีเซ็ต"},
    "parameters.unsaved":  {EN: "You have unsaved changes", TH: "มีการเปลี่ยนแปลงที่ยังไม่บันทึก"},

    "history.title": {EN: "History", TH: "ประวัติ"},
    "history.subtitle":    {EN: "Logged readings and dosing events", TH: "ค่าที่บันทึกไว้และประวัติการจ่ายปุ๋ย"},
    "history.doses_title": {EN: "Recent dosing events", TH: "การจ่ายปุ๋ยล่าสุด"},
    "history.no_doses":    {EN: "No dosing yet — nothing to report.", TH: "ยังไม่มีการจ่ายปุ๋ย"},
    "history.empty_chart": {EN: "Collecting data — check back soon", TH: "กำลังเก็บข้อมูล อีกสักครู่กลับมาดูใหม่"},

    "settings.title":         {EN: "Settings", TH: "ตั้งค่า"},
    "settings.subtitle":      {EN: "Profile, language and connections", TH: "โปรไฟล์ ภาษา และการเชื่อมต่อ"},
    "settings.crop_profile":  {EN: "Crop profile", TH: "โปรไฟล์พืช"},
    "settings.language":      {EN: "Language", TH: "ภาษา"},
    "settings.llm_connection": {EN: "LLM connection", TH: "การเชื่อมต่อ LLM"},
    "settings.profile_hint":  {EN: "Setpoints for this profile are edited on the Parameters page.",
                               TH: "แก้ไขค่าเป้าหมายของโปรไฟล์นี้ได้ที่หน้าพารามิเตอร์"},

    "parameters.subtitle": {EN: "Setpoints, dosing rules and calibration",
                            TH: "ค่าเป้าหมาย กฎการจ่ายปุ๋ย และการปรับเทียบ"},

    # Time-of-day greeting shown under the dashboard title.
    "greeting.morning":   {EN: "Good morning", TH: "สวัสดีตอนเช้า"},
    "greeting.afternoon": {EN: "Good afternoon", TH: "สวัสดีตอนบ่าย"},
    "greeting.evening":   {EN: "Good evening", TH: "สวัสดีตอนเย็น"},

    # Sensor status labels (get_status returns the English label).
    "status.normal":   {EN: "Normal", TH: "ปกติ"},
    "status.warning":  {EN: "Warning", TH: "เฝ้าระวัง"},
    "status.too_low":  {EN: "Too Low", TH: "ต่ำไป"},
    "status.too_high": {EN: "Too High", TH: "สูงไป"},

    # Sensor display names (keys stay English identifiers in code/config).
    "sensor.name.EC":          {EN: "EC", TH: "ค่าปุ๋ย (EC)"},
    "sensor.name.PH":          {EN: "pH", TH: "กรด-ด่าง (pH)"},
    "sensor.name.Temperature": {EN: "Temperature", TH: "อุณหภูมิ"},
    "sensor.name.Humidity":    {EN: "Humidity", TH: "ความชื้น"},
    "sensor.target":           {EN: "Target", TH: "เป้าหมาย"},
}

# get_status() label -> i18n key, so views can translate the returned label
# without changing the English identifiers used in code and the DB.
_STATUS_KEYS = {
    "Normal": "status.normal",
    "Warning": "status.warning",
    "Too Low": "status.too_low",
    "Too High": "status.too_high",
}


def t_status(label: str, lang: str = EN) -> str:
    """Translate a get_status() label; unknown labels pass through as-is."""
    key = _STATUS_KEYS.get(label)
    return t(key, lang) if key else label


def t(key: str, lang: str = EN) -> str:
    """Look up `key` in `lang`, falling back to English then the raw key."""
    entry = _STRINGS.get(key)
    if not entry:
        return key
    return entry.get(lang, entry.get(EN, key))
