# TradeLens Deploy Guide — Clean Version

Ye package **TradeLens** ka clean deploy version hai.

## Is version me kya hai?

- ✅ PRO Strategy
- ✅ Signals
- ✅ Backtest
- ✅ Intraday tools
- ✅ Options Greeks
- ✅ Paper Trading UI
- ✅ Angel One SmartAPI integration helpers
- ❌ Astro strategies hata di gayi hain

---

## GitHub par upload ka simple tarika

### Recommended: Repository delete mat karo
Pura `tredeline` repository delete karne ki zarurat nahi hai. Agar repo delete kar doge to Render ka connection toot sakta hai.

Best ye hai:
1. GitHub repo kholo: `github.com/gauravgupta4522-hub/tredeline`
2. `tradelens_deploy` folder me jao
3. Purani files replace/upload karo
4. `astro.py` agar dikh rahi ho to delete karo
5. Commit changes karo
6. Render auto deploy karega

---

## Agar aap bilkul fresh upload karna chahte ho

Agar aap puri repo ko clean karke dobara upload karna chahte ho, to dhyan rakho:

1. Repository ka naam same rakho: `tredeline`
2. Folder ka naam same rakho: `tradelens_deploy`
3. Render me Root Directory same honi chahiye: `tradelens_deploy`
4. Dockerfile `tradelens_deploy` folder ke andar hona chahiye

---

## Render settings

Root Directory:

```txt
tradelens_deploy
```

Dockerfile path automatic mil jana chahiye kyunki Dockerfile folder ke andar hai.

Agar manual command chahiye:

```txt
uvicorn server:app --host 0.0.0.0 --port $PORT
```

---

## Important

Ye app educational decision-support tool hai. Ye guaranteed profit ya 100% winning signals promise nahi karta. Trading me risk hota hai.
