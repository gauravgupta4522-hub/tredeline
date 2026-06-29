# 🌐 TradeLens ko ONLINE karo — link se kahin bhi kholo

Iske baad aapko **ek permanent link** milega (jaise `https://tradelens-xxx.onrender.com`)
jo aap **phone ya computer kisi bhi browser** me khol sakte ho — har baar kuch
chalane ki zaroorat nahi. **Bilkul free.**

> Lagega ~10 minute. Sirf 2 free account banane hain (GitHub + Render). Coding nahi.

---

## 📦 Step 0 — yeh folder taiyaar rakho
Aapke paas yeh folder hai: **`tradelens_deploy`**
Isme saari files hain (server.py, index.html, app.js, requirements.txt, render.yaml, etc.).
Bas isi folder ko online daalna hai.

---

## 🟢 Step 1 — GitHub account + folder upload (free)

1. Browser me kholo: **https://github.com/signup** → free account banao.
2. Login ke baad upar-right **"+"** → **"New repository"**.
3. Repository name likho: `tradelens` → niche **"Create repository"** dabao.
4. Agle page pe link dikhega: **"uploading an existing file"** — us par click karo.
5. Apne computer se **`tradelens_deploy` folder ke ANDAR ki saari files**
   (server.py, index.html, app.js, requirements.txt, render.yaml, icons folder, etc.)
   ko **drag-and-drop** karo us page pe.
6. Niche **"Commit changes"** (hara button) dabao.
   ✅ Ab aapka code GitHub pe aa gaya.

---

## 🔵 Step 2 — Render.com pe deploy (free, link milega)

1. Browser me kholo: **https://render.com** → **"Get Started"** → **"Sign in with GitHub"**
   (GitHub se hi login karo — easiest).
2. Dashboard pe upar **"New +"** → **"Web Service"** chuno.
3. Apna GitHub `tradelens` repo dikhega → uske saamne **"Connect"** dabao.
   (Pehli baar ho to "Configure GitHub" → repo access do.)
4. Render khud settings bhar lega (render.yaml ki wajah se). Confirm karo:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn server:app --host 0.0.0.0 --port $PORT`
   - **Instance Type:** **Free** chuno.
5. Niche **"Create Web Service"** (bada button) dabao.
6. 3-5 minute wait karo (build hoga — log chalta dikhega).
   Jab **"Live"** (hara) dikhe → ho gaya! 🎉

---

## 🎉 Step 3 — apna app kholo

Upar ek link dikhega, jaise:
```
https://tradelens-xxxx.onrender.com
```
- **Computer pe:** us link ko browser me kholo.
- **Phone pe:** wahi link phone browser me kholo → menu (⋮) → **"Add to Home Screen"**
  → ab phone pe app icon ban gaya! 📱

Ab top-right me **"online ✓"** dikhega — matlab sab kaam kar raha hai.
Dropdowns bhar jayenge, "Get Signal" / "Run Backtest" sab chalega.

---

## ⚠️ Free plan ki ek choti baat (normal hai)
Render ka free plan: agar 15 min koi use na kare to server "so jaata" hai.
Phir agli baar kholne par **pehli baar ~30-50 second loading** lega (jaag raha hota hai).
Uske baad fast. Yeh free me normal hai — paid plan ($7/mo) me yeh nahi hota.

---

## 🆘 Atak gaye?
- GitHub upload me dikkat → files ko folder ke **andar se** select karo, folder ko nahi.
- Render build "failed" → log me red line ka screenshot bhejo.
- "online ✓" nahi dikh raha → 1 min wait karke page refresh karo (server jaag raha hoga).

Kuch bhi atke to screenshot bhejo — main turant theek karwa dunga. 👍

---
*Educational tool · Not investment advice · Koi strategy daily guaranteed profit nahi deti.*
