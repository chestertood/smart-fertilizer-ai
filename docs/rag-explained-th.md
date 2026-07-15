# RAG กับระบบความรู้พืชของ Farm Assistant (อธิบายภาษาไทย)

เอกสารนี้อธิบายว่าระบบ RAG (Retrieval-Augmented Generation) ในโปรเจคนี้ทำงานอย่างไร
ตั้งแต่แนวคิดจนถึงไฟล์จริง เพื่อให้ต่อยอด/แก้ไขได้เอง

---

## 1. RAG คืออะไร / ทำไมต้องใช้

LLM (เช่น Claude) จำความรู้จากตอนเทรนไว้ในตัวเอง แต่:

- ความรู้ **ไม่ครบ** — เรื่องเฉพาะทาง เช่น ค่า EC/pH ที่เหมาะกับผักบุ้งในระบบไฮโดรของเรา โมเดลอาจไม่รู้ละเอียด
- ความรู้ **ไม่อัปเดต** — ถ้าเราปรับสูตรปุ๋ยเอง โมเดลไม่มีทางรู้
- โมเดล **เดา (hallucinate)** เมื่อไม่รู้จริง

**RAG** แก้ปัญหานี้โดยเก็บความรู้ไว้ **นอกโมเดล** แล้วดึงเฉพาะส่วนที่เกี่ยวข้องกับคำถามมาแปะเข้า prompt ก่อนให้โมเดลตอบ โมเดลจึงตอบจากข้อมูลจริงที่เราคุมได้

วงจร RAG 4 ขั้น:

```
Index    → แปลงความรู้ทั้งหมดเป็น vector เก็บไว้ (ทำครั้งเดียว/เมื่อแก้ข้อมูล)
Retrieve → รับคำถาม ดึง chunk ที่เกี่ยวข้องที่สุดออกมา
Augment  → เอา chunk ที่ได้ไปแปะต่อท้าย prompt
Generate → โมเดลตอบโดยอ้างอิงความรู้ที่แปะให้
```

---

## 2. Embedding

**Embedding** = การแปลงข้อความเป็น **vector** (ตัวเลขหลายร้อยมิติ) ที่จับ "ความหมาย" ของข้อความ
หลักการสำคัญ: **ข้อความที่มีความหมายใกล้กัน → vector อยู่ใกล้กัน** ในปริภูมิหลายมิติ

เช่น "kale ต้องการ EC สูง" กับ "คะน้าชอบค่าความเข้มข้นปุ๋ยสูง" จะได้ vector ที่ใกล้กัน
แม้ใช้คำคนละคำ นี่คือเหตุผลว่าทำไม RAG ค้นได้ตามความหมาย ไม่ใช่แค่ match คำตรงตัว

โปรเจคนี้ใช้ **Voyage `voyage-3`**:

- เป็นโมเดล embedding แบบ **multilingual** — รองรับภาษาไทย จึงค้นความรู้ที่ปนไทย/อังกฤษได้
- เรียกผ่าน API (ไม่ต้องรันโมเดลเอง)

**ทำไมไม่ใช้ embedding แบบ local?** เพราะเป้าหมายรันบน **Raspberry Pi 5 (ARM64)** —
โมเดล embedding local ส่วนใหญ่ต้องใช้ `torch` ซึ่งหนักเกินไปสำหรับ Pi API-based จึงเบากว่ามาก

**ทำไมต้องใช้ API key แยกจาก Anthropic?** เพราะ **Anthropic (Claude) ไม่มี endpoint สำหรับ embedding** —
Claude ใช้ generate คำตอบ ส่วนงาน embedding ต้องพึ่งผู้ให้บริการ embedding โดยเฉพาะ (ที่นี่คือ Voyage)
จึงต้องมี `VOYAGE_API_KEY` แยกต่างหากใน `.env`

---

## 3. Cosine similarity + ตัวอย่างจริง

จะรู้ว่า vector สองอันใกล้กันแค่ไหน ใช้ **cosine similarity** — วัด "มุม" ระหว่าง vector:

```
cos(A, B) = (A · B) / (|A| × |B|)
```

- `A · B` = dot product
- `|A|`, `|B|` = ความยาว (norm) ของ vector
- ผลลัพธ์อยู่ระหว่าง -1 ถึง 1 — **ยิ่งใกล้ 1 ยิ่งเหมือน**

**ตัวอย่างจริง** (จากเทสต์ `tests/test_knowledge.py`) — query = `[1, 0, 0]`:

| doc vector    | cosine กับ query | ความหมาย                    |
|---------------|------------------|-----------------------------|
| `[1, 0, 0]`   | **1.0**          | เหมือนเป๊ะ ทิศเดียวกัน       |
| `[0, 1, 0]`   | **0.0**          | ตั้งฉาก ไม่เกี่ยวกันเลย      |
| `[0.9, 0.1, 0]` | **≈ 0.994**    | เกือบเหมือน จึงถูกจัดอันดับรองลงมา |

คำนวณอันสุดท้าย: `(1×0.9 + 0×0.1 + 0×0) / (1 × √(0.9²+0.1²)) = 0.9 / 0.9055 ≈ 0.994`

**ทำไมต้อง normalize?** ถ้าไม่หารด้วยความยาว vector ที่ "ยาว" กว่า (ค่ามากกว่า) จะได้ dot product สูงเกินจริง
ทั้งที่ทิศทาง (=ความหมาย) อาจไม่ได้ใกล้กว่า การ normalize ทำให้เทียบกันที่ **ทิศทางล้วน ๆ** เป็นธรรม
ในโค้ด `_cosine_top_k` ทำ normalize ทั้ง query และทุกแถวของ matrix ก่อนคูณกัน

---

## 4. Chunking ในโปรเจคนี้

"Chunk" = หน่วยความรู้ 1 ก้อนที่เอาไป embed โปรเจคนี้แบ่งดังนี้:

- **Seed JSON:** พืช 1 ตัว = **1 chunk** — ฟังก์ชัน `_crop_to_text()` แปลง dict ของพืช
  (ชื่อ + ทุก stage + ค่า target + notes) เป็นข้อความอ่านง่ายก้อนเดียว
- **PDF:** **1 หน้า = 1 chunk** — `_pdf_chunks()` ดึงข้อความทีละหน้า หน้าที่อ่านไม่ได้ก็ข้าม (best-effort)

**เหตุผลของ granularity นี้:** ข้อมูลพืช 1 ตัวมีขนาดพอดี — เล็กพอให้ retrieve เจาะจงได้
(ถามเรื่องคะน้า ก็ดึงเฉพาะ chunk คะน้า) แต่ใหญ่พอให้ context ครบ (ทุก stage อยู่ด้วยกัน)
ส่วน PDF แบ่งรายหน้าเพราะเป็นหน่วยธรรมชาติ และกันไม่ให้ chunk ใหญ่เกินจนความหมายเจือจาง

---

## 5. numpy vs vector database

โปรเจคนี้เก็บ vector ทั้งหมดเป็นไฟล์ `.npz` แล้วค้นด้วย **numpy brute-force cosine** —
คือคำนวณ cosine กับ *ทุก* chunk แล้วเรียงลำดับ

- ที่จำนวนไม่กี่ร้อย chunk การ brute-force เร็วระดับ **มิลลิวินาที** — ไม่ต่างจาก vector DB ที่รู้สึกได้
- **ไม่ต้องลง dependency หนัก** บน Pi (ไม่มี Chroma/FAISS/torch) — แค่ numpy
- Vector DB แบบ ANN (Approximate Nearest Neighbor) เช่น Chroma/FAISS **คุ้มก็ต่อเมื่อ chunk เกินหลักพัน**
  ตอนนั้น brute-force เริ่มช้าและ ANN ช่วยได้จริง

การตัดสินใจนี้บันทึกไว้เป็น `# ponytail` comment ใน `app/services/knowledge.py`:

```
# ponytail: numpy brute-force cosine; swap to Chroma/FAISS if chunks exceed ~5000
```

= ถ้าวันหนึ่ง chunk ทะลุ ~5000 ค่อยเปลี่ยนไป Chroma/FAISS จนกว่าถึงตอนนั้น numpy พอ

---

## 6. แผนที่ไฟล์

| ไฟล์ | หน้าที่ |
|------|---------|
| `knowledge/crops_seed.json` | ความรู้พืชตั้งต้น (seed) — แก้/เพิ่มพืชที่นี่ |
| `knowledge/*.pdf` | ทิ้ง PDF ความรู้เพิ่มลงโฟลเดอร์นี้ (optional) |
| `app/services/knowledge.py` | หัวใจ RAG — ดูฟังก์ชันด้านล่าง |
| &nbsp;&nbsp;• `_embed(texts, input_type)` | เรียก Voyage แปลงข้อความ → vector |
| &nbsp;&nbsp;• `_cosine_top_k(q, matrix, k)` | คืน index+score ของ k chunk ที่ใกล้ที่สุด |
| &nbsp;&nbsp;• `build_index()` | โหลด chunk ทั้งหมด → embed → เซฟ `.npz` |
| &nbsp;&nbsp;• `retrieve(query, k)` | รับคำถาม → ดึง chunk ที่เกี่ยวข้อง (best-effort, fail → `[]`) |
| `build_knowledge.py` | สคริปต์ CLI เรียก `build_index()` (รันตอน setup/แก้ข้อมูล) |
| `data/knowledge_index.npz` | ไฟล์ index ที่ build ออกมา (git-ignored — ไม่ commit) |
| `app/services/llm_agent.py` | จุด inject ความรู้เข้า prompt: |
| &nbsp;&nbsp;• `_knowledge_block(query)` | เรียก `retrieve` แล้ว format เป็นบล็อกความรู้ |
| &nbsp;&nbsp;• `recommend()` | แปะบล็อกความรู้ต่อท้าย prompt แนะนำการโดสปุ๋ย |
| &nbsp;&nbsp;• `chat()` | แปะบล็อกความรู้ตามคำถามล่าสุดของผู้ใช้ |

---

## 7. วิธีใช้จริง

```bash
# 1. ติดตั้ง dependencies (มี voyageai, pypdf, numpy)
pip install -r requirements.txt

# 2. ใส่ API key ใน .env
echo "VOYAGE_API_KEY=pa-xxxxxxxx" >> .env

# 3. build index (ทำครั้งแรก และทุกครั้งที่แก้ความรู้)
python build_knowledge.py
```

**เติมความรู้ใหม่:**

- แก้ค่า/เพิ่มพืช → แก้ `knowledge/crops_seed.json`
- เพิ่มเอกสารความรู้ → ทิ้งไฟล์ `.pdf` ลง `knowledge/`
- จากนั้น **รัน `python build_knowledge.py` ใหม่** เพื่อ re-index

หลังจากนั้นทุกครั้งที่ `recommend()` หรือ `chat()` ถูกเรียก ระบบจะดึงความรู้ที่เกี่ยวข้อง
มาแปะให้ Claude อัตโนมัติ ถ้า index หาย/ไม่มี key ระบบ **ยังทำงานได้ปกติ** เพียงตอบโดยไม่มี grounding
(retrieve คืน `[]` แบบเงียบ ๆ)
