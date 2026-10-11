#!/usr/bin/env python3
# UPeL → powiadomienia na telefonie (Web Push do aplikacji Notatki). Uruchamia .github/workflows/upel.yml co 15 minut.
# Co sprawdza: powiadomienia samego UPeL-a (ogłoszenia, terminy, oceny) i nowe materiały w kursach (core_course_get_contents).
# Sekrety: UPEL_TOKEN – token aplikacji mobilnej Moodle (~/SimpleAGH/tools/upel_push.py token), VAPID_PRIVATE_KEY – klucz PEM,
#          PUSH_SUBS – lista subskrypcji z aplikacji (JSON; ~/SimpleAGH/tools/upel_push.py subs).
# Stan (co już było) w state/upel.json – tylko skróty identyfikatorów, trzymany w pamięci podręcznej Actions, nie w repo.
# Log jest publiczny, więc wypisuje tylko liczby. Pierwsze uruchomienie niczego nie wysyła, tylko zapamiętuje.
# Lokalnie: UPEL_TOKEN=… VAPID_PRIVATE_KEY="$(cat …pem)" PUSH_SUBS='[…]' python3 upel_watch.py [--test]
import hashlib, html, json, os, re, sys, tempfile, time, urllib.parse, urllib.request

API = "https://upel.agh.edu.pl/webservice/rest/server.php"
STATE = "state/upel.json"
NAMES = {12618: "Programowanie", 12737: "Algebra", 13142: "Algebra", 12294: "Logika", 12918: "Logika", 12836: "Unix"}
SKIP = {5344}   # szkolenie BHP
MAX = 5         # więcej nowości naraz → jedno zbiorcze powiadomienie


def ws(fn, **a):
    data = urllib.parse.urlencode({"wstoken": os.environ["UPEL_TOKEN"], "wsfunction": fn, "moodlewsrestformat": "json", **a}).encode()
    for k in range(3):
        try:
            r = json.loads(urllib.request.urlopen(API, data, timeout=40).read())
            break
        except Exception:
            if k == 2: raise
            time.sleep(10)
    if isinstance(r, dict) and r.get("exception"): raise RuntimeError(r.get("errorcode") or "ws")
    return r


def key(s): return hashlib.sha256(s.encode()).hexdigest()[:16]


def clean(s): return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def send(items):
    from pywebpush import webpush, WebPushException
    subs = json.loads(os.environ.get("PUSH_SUBS") or "[]")
    pem = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False); pem.write(os.environ["VAPID_PRIVATE_KEY"]); pem.close()
    ok = bad = 0
    for it in items:
        for s in subs:
            try:
                webpush(subscription_info=s, data=json.dumps(it, ensure_ascii=False), vapid_private_key=pem.name,
                        vapid_claims={"sub": "https://juzu01.github.io"}, ttl=2 * 86400, headers={"Urgency": "high"})
                ok += 1
            except WebPushException as e:
                r = getattr(e, "response", None)
                bad += 1; print("push: błąd", getattr(r, "status_code", "?"), (getattr(r, "text", "") or "")[:80])   # np. 410 = telefon wyłączył powiadomienia
    os.unlink(pem.name)
    print(f"wysłane: {ok}, błędy: {bad}, subskrypcji: {len(subs)}")


def main():
    if "--test" in sys.argv:
        return send([{"title": "Notatki", "body": "Powiadomienia z UPeL-a działają.", "url": "/notatki/", "tag": "test"}])
    os.makedirs("state", exist_ok=True)
    st = json.load(open(STATE)) if os.path.exists(STATE) else None
    seen = set(st["seen"]) if st else set()
    try:
        uid = ws("core_webservice_get_site_info")["userid"]
    except RuntimeError as e:   # token wygasł albo cofnięty: jedno przypomnienie na dobę
        print("UPeL: token nie działa")
        day = time.strftime("%Y-%m-%d")
        if st is not None and st.get("tokwarn") != day:
            send([{"title": "UPeL", "body": "Sprawdzanie UPeL-a przestało działać – trzeba odnowić token (napisz do Claude'a).", "url": "/notatki/", "tag": "token"}])
            st["tokwarn"] = day; json.dump(st, open(STATE, "w")); print("changed=1", file=open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a"))
        return
    new = []
    for n in ws("message_popup_get_popup_notifications", useridto=uid, limit=40).get("notifications", []):   # to, co UPeL sam pokazuje w dzwoneczku
        k = key(f"n{n['id']}")
        if k in seen: continue
        seen.add(k)
        new.append({"t": n.get("timecreated", 0), "title": "UPeL", "body": clean(n.get("subject")),
                    "url": n.get("contexturl") or "https://upel.agh.edu.pl/message/output/popup/notifications.php", "tag": f"n{n['id']}"})
    for c in ws("core_enrol_get_users_courses", userid=uid):
        if c["id"] in SKIP: continue
        name, fresh = NAMES.get(c["id"], clean(c.get("shortname"))), []
        for sec in ws("core_course_get_contents", courseid=c["id"]):
            for m in sec.get("modules", []):
                if m.get("modname") == "label" or not m.get("uservisible", True): continue
                k = key(f"m{m['id']}")
                if k in seen: continue
                seen.add(k); fresh.append(m)
        if len(fresh) > 2:
            new.append({"t": time.time(), "title": name, "body": f"{len(fresh)} nowe rzeczy na UPeL-u, m.in. {clean(fresh[0]['name'])}",
                        "url": f"https://upel.agh.edu.pl/course/view.php?id={c['id']}", "tag": f"c{c['id']}"})
        for m in fresh if len(fresh) <= 2 else []:
            new.append({"t": m.get("added") or time.time(), "title": name, "body": f"Nowe na UPeL-u: {clean(m['name'])}",
                        "url": m.get("url") or f"https://upel.agh.edu.pl/course/view.php?id={c['id']}", "tag": f"m{m['id']}"})
    changed = st is None or bool(new) or len(seen) != len(st.get("seen", []))
    if st is not None and new:
        new.sort(key=lambda x: x["t"])
        if len(new) > MAX:
            new = [{"title": "UPeL", "body": f"{len(new)} nowości na UPeL-u: " + "; ".join(x["body"] for x in new[:3]) + " …", "url": "/notatki/", "tag": "wiele"}]
        send([{k: v for k, v in x.items() if k != "t"} for x in new])
    print(("pierwsze uruchomienie – zapamiętane" if st is None else f"nowe: {len(new)}"), f"(znanych: {len(seen)})")
    if changed:
        json.dump({"seen": sorted(seen), "tokwarn": (st or {}).get("tokwarn")}, open(STATE, "w"))
        print("changed=1", file=open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a"))


if __name__ == "__main__":
    main()
