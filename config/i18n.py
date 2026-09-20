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
    "nav.exit":       {EN: "Exit", TH: "ออกจากโปรแกรม"},

    # Kiosk-mode exit confirm (the window has no title bar to close).
    "exit.title":  {EN: "Exit app?", TH: "ออกจากโปรแกรม?"},
    "exit.body":   {EN: "Sensor monitoring and logging stop until the app is started again.",
                    TH: "การอ่านค่าเซนเซอร์และการบันทึกข้อมูลจะหยุด จนกว่าจะเปิดโปรแกรมใหม่"},
    "exit.cancel": {EN: "Cancel", TH: "ยกเลิก"},
    "exit.confirm": {EN: "Exit", TH: "ออก"},

    "startup.connecting": {EN: "Connecting to sensors…", TH: "กำลังเชื่อมต่อเซนเซอร์…"},

    "dashboard.title":    {EN: "Sensor Dashboard", TH: "แดชบอร์ดเซนเซอร์"},
    "dashboard.subtitle": {EN: "Real-time monitoring", TH: "ติดตามผลแบบเรียลไทม์"},
    "dashboard.online":   {EN: "Online", TH: "ออนไลน์"},
    "dashboard.offline":  {EN: "Offline", TH: "ออฟไลน์"},
    "dashboard.tank_capacity": {EN: "Tank Capacity", TH: "ความจุถัง"},
    "dashboard.tank_dims": {EN: "{w}×{l}×{h} cm reservoir", TH: "ถังขนาด {w}×{l}×{h} ซม."},

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
    "history.dose_ai":     {EN: "AI dose", TH: "AI จ่ายให้"},
    "history.dose_manual": {EN: "Manual dose", TH: "จ่ายเอง"},
    "history.over":     {EN: "▲ over {min:.0f} min", TH: "▲ เกิน {min:.0f} นาที"},
    "history.under":    {EN: "▼ under {min:.0f} min", TH: "▼ ต่ำ {min:.0f} นาที"},
    "history.in_range": {EN: "in range", TH: "อยู่ในช่วง"},
    "history.empty_chart": {EN: "Collecting data — check back soon", TH: "กำลังเก็บข้อมูล อีกสักครู่กลับมาดูใหม่"},

    "settings.title":         {EN: "Settings", TH: "ตั้งค่า"},
    "settings.subtitle":      {EN: "Profile, language and connections", TH: "โปรไฟล์ ภาษา และการเชื่อมต่อ"},
    "settings.crop_profile":  {EN: "Crop profile", TH: "โปรไฟล์พืช"},
    "settings.language":      {EN: "Language", TH: "ภาษา"},
    "settings.llm_connection": {EN: "LLM connection", TH: "การเชื่อมต่อ LLM"},
    "settings.profile_hint":  {EN: "Setpoints for this profile are edited on the Parameters page.",
                               TH: "แก้ไขค่าเป้าหมายของโปรไฟล์นี้ได้ที่หน้าพารามิเตอร์"},
    "settings.llm_mode":      {EN: "LLM dosing mode", TH: "โหมดการจ่ายปุ๋ยของ LLM"},
    "settings.mode_approval": {EN: "Approval — dosing waits for your tap",
                               TH: "อนุมัติ — รอการกดยืนยันก่อนจ่ายปุ๋ย"},
    "settings.mode_auto":     {EN: "Auto-dose — dosing applies immediately",
                               TH: "จ่ายอัตโนมัติ — จ่ายปุ๋ยทันทีโดยไม่ต้องยืนยัน"},
    "settings.mode_hint":     {EN: "Config changes (rules, growth stages, targets, "
                                   "calibration) always need approval, in either mode.",
                               TH: "การเปลี่ยนค่าตั้งค่า (กฎ ระยะการเจริญเติบโต เป้าหมาย "
                                   "การปรับเทียบ) ต้องยืนยันเสมอ ไม่ว่าจะโหมดใด"},

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

    # -- shared button / dialog words ----------------------------------------
    "common.cancel": {EN: "Cancel", TH: "ยกเลิก"},
    "common.delete": {EN: "Delete", TH: "ลบ"},
    "common.create": {EN: "Create", TH: "สร้าง"},
    "common.name":   {EN: "Name", TH: "ชื่อ"},

    # -- Auto-dose confirm (app bar + Settings show the same dialog) ---------
    "mode.enable_title": {EN: "Enable Auto-dose mode?", TH: "เปิดโหมดจ่ายปุ๋ยอัตโนมัติ?"},
    "mode.enable_body": {
        EN: "LLM-proposed dosing will apply immediately, with no approval tap — "
            "on Telegram and in this app. Config changes (auto-dose rules, growth "
            "stages, targets, calibration) still always need approval, in either mode.",
        TH: "คำแนะนำการจ่ายปุ๋ยจาก AI จะทำงานทันทีโดยไม่ต้องกดอนุมัติ ทั้งใน Telegram "
            "และในแอปนี้ ส่วนการแก้ไขค่าตั้งค่า (กฎอัตโนมัติ ระยะการเติบโต ค่าเป้าหมาย "
            "การคาลิเบรต) ยังต้องกดอนุมัติเสมอในทุกโหมด",
    },
    "mode.enable_confirm": {EN: "Turn on Auto-dose", TH: "เปิดโหมดอัตโนมัติ"},

    # -- chat assistant -------------------------------------------------------
    "chat.title":        {EN: "Farm Assistant", TH: "ผู้ช่วยฟาร์ม"},
    "chat.placeholder":  {EN: "Ask anything…", TH: "ถามอะไรก็ได้…"},
    "chat.approve":      {EN: "Approve", TH: "อนุมัติ"},
    "chat.send":         {EN: "Send", TH: "ส่ง"},
    "chat.attach":       {EN: "Attach file or image", TH: "แนบไฟล์หรือรูป"},
    "chat.thinking":     {EN: "Thinking…", TH: "กำลังคิด…"},
    "chat.check_status": {EN: "Check status", TH: "ดูสถานะ"},
    "chat.recommend":    {EN: "Recommend dosing", TH: "ขอคำแนะนำการจ่ายปุ๋ย"},

    # -- Parameters page ------------------------------------------------------
    "parameters.setpoints_hint": {
        EN: "Normal range per sensor. The dot shows the live status against your range.",
        TH: "ช่วงปกติของแต่ละเซนเซอร์ จุดสีบอกสถานะสดเทียบกับช่วงที่ตั้งไว้",
    },
    "parameters.reset_defaults": {EN: "Reset to profile defaults",
                                  TH: "คืนค่าเริ่มต้นของโปรไฟล์"},
    "parameters.rule_if":     {EN: "if sensor", TH: "ถ้าเซนเซอร์"},
    "parameters.rule_is":     {EN: "is", TH: "เป็น"},
    "parameters.rule_value":  {EN: "value", TH: "ค่า"},
    "parameters.rule_then":   {EN: "then dose", TH: "แล้วจ่าย"},
    "parameters.delete_rule": {EN: "Delete rule", TH: "ลบกฎ"},
    "parameters.rules_hint": {
        EN: "Rules are saved now; automatic execution is a later phase. "
            "For now they document your intended logic.",
        TH: "ตอนนี้กฎถูกบันทึกไว้เฉยๆ การสั่งงานอัตโนมัติจะมาในเฟสถัดไป "
            "ระหว่างนี้ใช้เป็นบันทึกแนวคิดที่ตั้งใจไว้",
    },
    "parameters.add_rule":  {EN: "Add rule", TH: "เพิ่มกฎ"},
    "parameters.dose":      {EN: "Dose", TH: "จ่าย"},
    "parameters.dose_hint": {EN: "Trigger a pump by hand. Dispensing is logged to History.",
                             TH: "สั่งปั๊มด้วยมือ ทุกครั้งที่จ่ายจะถูกบันทึกในหน้าประวัติ"},
    "parameters.calib_hint": {EN: "Pump throughput and sensor calibration offsets.",
                              TH: "อัตราการจ่ายของปั๊มและค่าชดเชยการคาลิเบรตเซนเซอร์"},
    "parameters.pumps":          {EN: "Pumps", TH: "ปั๊ม"},
    "parameters.sensor_offsets": {EN: "Sensor offsets", TH: "ค่าชดเชยเซนเซอร์"},
    "parameters.reservoir":      {EN: "Reservoir tank", TH: "ถังพัก"},
    "parameters.tank_hint": {
        EN: "Enter the reservoir's inner dimensions. Capacity feeds the chat "
            "assistant's dosing math.",
        TH: "กรอกขนาดภายในของถัง ความจุที่ได้จะถูกใช้คำนวณปริมาณการจ่ายของผู้ช่วย AI",
    },
    "parameters.stage_name":   {EN: "Stage name", TH: "ชื่อระยะ"},
    "parameters.delete_stage": {EN: "Delete stage", TH: "ลบระยะ"},
    "parameters.growth_hint": {
        EN: "Define growth stages (e.g. seedling / growing / mature) with their own "
            "target ranges; the active stage drives the dashboard.",
        TH: "กำหนดระยะการเติบโต (เช่น ต้นกล้า / เจริญเติบโต / โตเต็มที่) "
            "พร้อมช่วงเป้าหมายของแต่ละระยะ ระยะปัจจุบันจะถูกใช้บนแดชบอร์ด",
    },
    "parameters.start_planting": {EN: "Start planting today", TH: "เริ่มปลูกวันนี้"},
    "parameters.stop_tracking":  {EN: "Stop tracking", TH: "หยุดติดตาม"},
    "parameters.stages":         {EN: "Stages", TH: "ระยะ"},
    "parameters.duration_days":  {EN: "Duration (days)", TH: "ระยะเวลา (วัน)"},
    "parameters.add_stage":      {EN: "Add stage", TH: "เพิ่มระยะ"},

    # Feedback lines (snack bars / inline status).
    "parameters.saved":        {EN: "Saved", TH: "บันทึกแล้ว"},
    "parameters.numbers_only": {EN: "Numbers only — fix the boxes outlined in red",
                                TH: "กรอกได้เฉพาะตัวเลข — แก้ช่องที่ขอบแดง"},
    "parameters.planting_started": {EN: "Planting started today", TH: "เริ่มนับวันปลูกวันนี้"},
    "parameters.tracking_stopped": {EN: "Growth tracking stopped", TH: "หยุดติดตามการเติบโตแล้ว"},
    "parameters.bad_number":   {EN: "{pump}: enter a valid number",
                                TH: "{pump}: กรอกตัวเลขให้ถูกต้อง"},
    "parameters.dispensed":    {EN: "Dispensed {amount:.1f} ml from {pump}",
                                TH: "จ่าย {amount:.1f} มล. จาก {pump} แล้ว"},

    # -- Settings page --------------------------------------------------------
    "settings.new_profile":      {EN: "New crop profile", TH: "โปรไฟล์พืชใหม่"},
    "settings.profile_name":     {EN: "Profile name", TH: "ชื่อโปรไฟล์"},
    "settings.new_profile_hint": {
        EN: "Starts with generic EC/pH/Temperature/Humidity ranges — adjust them on "
            "the Parameters page.",
        TH: "เริ่มจากช่วง EC/pH/อุณหภูมิ/ความชื้น แบบทั่วไป — ปรับได้ที่หน้าพารามิเตอร์",
    },
    "settings.delete_profile_q": {EN: "Delete profile?", TH: "ลบโปรไฟล์?"},
    "settings.delete_profile_body": {
        EN: "This permanently deletes the profile and its saved setpoints. "
            "This cannot be undone.",
        TH: "การลบจะเอาโปรไฟล์และค่าตั้งต้นที่บันทึกไว้ออกถาวร ย้อนกลับไม่ได้",
    },
    "settings.delete_profile_tip": {EN: "Delete this profile", TH: "ลบโปรไฟล์นี้"},

    "sensor.target":           {EN: "Target", TH: "เป้าหมาย"},
    "sensor.no_signal":        {EN: "No signal", TH: "ไม่มีสัญญาณ"},

    "settings.appearance":  {EN: "Appearance", TH: "การแสดงผล"},
    "settings.theme_light": {EN: "Light", TH: "โหมดสว่าง"},
    "settings.theme_dark":  {EN: "Dark", TH: "โหมดมืด"},
    "settings.theme_hint":  {EN: "Dark mode is easier on the eyes at night in the greenhouse.",
                             TH: "โหมดมืดถนอมสายตาเวลาใช้งานกลางคืนในโรงเรือน"},
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
