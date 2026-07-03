# Knowledge Base — Smart Farm Fertigation

โฟลเดอร์นี้เก็บความรู้เกษตร (agronomy knowledge) แบบข้อความ (Markdown) สำหรับป้อนเข้า
prompt ของ Claude ใน [llm_agent.py](../app/services/llm_agent.py) — เป็น **in-context
knowledge ไม่ใช่ training data** ไม่ต้อง fine-tune โมเดล แค่แนบ text เข้า prompt ตอนเรียก
API ทุกครั้ง

## โครงสร้าง

```
knowledge/
  tropical/               # พืชเมืองร้อน — อุณหภูมิสูง ความชื้นสูง โตเร็ว
    leafy_greens.md         # ผักใบ (ผักกาด คะน้า สลัด)
    fruiting_vegetables.md  # พืชออกผล (มะเขือเทศ พริก แตงกวา)
    herbs.md                 # สมุนไพร/ผักสวนครัว (โหระพา กะเพรา)
  temperate/              # พืชเมืองหนาว — ต้องการอุณหภูมิต่ำกว่า ไวต่อความร้อน
    leafy_greens.md
    fruiting_vegetables.md
    herbs.md
  general/
    smart_farm_fertigation_basics.md   # หลักการทั่วไป ใช้ทุก profile ทุกภูมิอากาศ
```

## หลักการเขียนไฟล์ในนี้ (สำคัญ)

เขียนแบบ **อธิบายเหตุผล ไม่ใช่แค่ยัดตัวเลข** — Claude ใช้เหตุผลพวกนี้ตัดสินสถานการณ์ที่ไม่ตรง
กับ rule ตรงๆ ได้ดีกว่าการยัด threshold ดิบๆ

โฟกัสเนื้อหาที่ **เกี่ยวกับระบบ smart farm ของเราโดยตรง**:
- พฤติกรรม EC / pH ของพืชกลุ่มนี้ (ขึ้น/ลงเร็วแค่ไหน ตอบสนองต่อ dosing ยังไง)
- ช่วง Temperature / Humidity ที่เหมาะสม และผลถ้าหลุดช่วง
- ข้อควรระวังตอนสั่ง dose (เช่น ห้าม dose ปุ๋ย A/B พร้อมกัน, ขนาด dose ต่อครั้งที่ปลอดภัย)
- เชื่อมกับปั๊มที่มีจริงใน [actuators.py](../app/services/actuators.py):
  `Nutrient A`, `Nutrient B`, `pH Up`, `pH Down`, `Water`

**ไม่ต้อง**ใส่ความรู้เกษตรทั่วไปที่ไม่เกี่ยวกับ hydroponic/fertigation (เช่น โรคพืช แมลงศัตรูพืช
การปลูกในดิน) — นอกขอบเขตระบบนี้

## การเชื่อมเข้าโค้ด (ยังไม่ทำ — ขั้นต่อไป)

ไฟล์พวกนี้ยังไม่ถูกอ่านโดยโค้ดอัตโนมัติ ขั้นต่อไปคือแก้ `_build_prompt()` ใน
[llm_agent.py](../app/services/llm_agent.py) ให้เปิดไฟล์ตาม active crop profile
(เทียบกับ `CROP_PROFILES` ใน [profiles.py](../config/profiles.py)) แล้วต่อท้าย prompt
ก่อนส่งไป Claude
