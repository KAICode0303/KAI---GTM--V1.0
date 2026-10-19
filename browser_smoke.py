"""Browser smoke test for the running app (Welcome, 3D Hoomi, chat, navigation, dark mode, phone width). Prints a JSON report, saves screenshots.

    HF_HUB_OFFLINE=1 .venv312/bin/python -m streamlit run app.py --server.port 8501 &
    python browser_smoke.py [http://localhost:8501]        (needs: pip install playwright; Google Chrome; software WebGL is fine)
"""
import json, os, sys, time
from playwright.sync_api import sync_playwright
os.makedirs("docs/screenshots/v3", exist_ok=True)
SC="docs/screenshots/v3/"
URL=sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8501"
out={}
def probes(pg):
    res=[]
    for f in pg.frames:
        if "hoomi3d.html" in f.url:
            try: res.append(f.evaluate("window.__hoomi"))
            except Exception as e: res.append({"err":str(e)})
    return res
with sync_playwright() as p:
    b=p.chromium.launch(channel="chrome",args=["--use-gl=angle","--use-angle=swiftshader","--enable-unsafe-swiftshader","--ignore-gpu-blocklist"])
    pg=b.new_page(viewport={"width":1440,"height":900})
    errs=[]; pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(URL); pg.wait_for_selector("text=Meet Hoomi",timeout=60000); pg.wait_for_timeout(4000)
    pr=probes(pg); out["welcome_probes"]=[{k:v for k,v in x.items() if k in("mode","ready","webgl","frames","blinks")} for x in pr]
    out["sidebar_items_on_welcome"]=[t for t in ["Executive Pulse","Ask Hoomi","GTM Workspace","Market Intelligence","SDR Activity","Command Center","Accounts & Prospecting","Content & Collaterals","Leads & Opportunities","Revenue & GP","About"] if pg.locator("[data-testid=stSidebar]").get_by_text(t).count()]
    pg.screenshot(path=SC+"app_welcome.png")
    # interactivity: pointer far to the right/top moves the head yaw
    hero=[f for f in pg.frames if "mode=hero" in f.url][0]
    y0=hero.evaluate("window.__hoomi.yaw")
    pg.mouse.move(1400,60); pg.wait_for_timeout(1200); y1=hero.evaluate("window.__hoomi.yaw")
    pg.mouse.move(40,800); pg.wait_for_timeout(1200); y2=hero.evaluate("window.__hoomi.yaw")
    out["hero_yaw_right_left"]=[round(y0,3),round(y1,3),round(y2,3)]
    out["blinks_after"]=hero.evaluate("window.__hoomi.blinks"); out["tail_angle"]=round(hero.evaluate("window.__hoomi.tailAngle"),3)
    # click the floating cat -> opens Ask Hoomi
    fab=[f for f in pg.frames if "mode=fab" in f.url][0]
    box=pg.locator(".st-key-hoomi_fab3d").bounding_box(); out["fab_box"]=box
    pg.mouse.click(box["x"]+box["width"]/2, box["y"]+box["height"]/2)
    pg.wait_for_selector("text=Ask Hoomi >> nth=0",timeout=30000)
    pg.wait_for_selector("[data-testid=stChatInput]",timeout=60000); pg.wait_for_timeout(2500)
    out["chat_opened_by_fab"]=pg.locator("[data-testid=stChatInput]").count()==1
    pg.screenshot(path=SC+"app_chat_empty.png")
    # ask a question
    pg.get_by_text("Which buyer personas should we target at a speech AI company?").first.click()
    pg.wait_for_selector("text=Technical Details",timeout=60000); pg.wait_for_timeout(1500)
    pg.screenshot(path=SC+"app_chat_answer.png")
    pg.locator("[data-testid=stExpander]").filter(has_text="Technical Details").first.locator("summary").click(); pg.wait_for_timeout(600)
    pg.screenshot(path=SC+"app_chat_technical.png")
    out["seven_sources_visible"]=sum(pg.get_by_text(f).count()>0 for f in ["01_capabilities.md","02_icp_model_evaluation.md","03_icp_multilingual_speech_audio.md","04_icp_robotics.md","05_case_study_model_evaluation.md","06_case_study_physical_ai.md","07_case_study_multilingual.md"])
    # typed refusals
    ci=pg.locator("[data-testid=stChatInput] textarea"); ci.fill("What is Kai's Company's hourly price?"); ci.press("Enter"); pg.wait_for_timeout(5000)
    pg.screenshot(path=SC+"app_chat_refusal.png")
    out["refusal_shown"]=pg.get_by_text("Insufficient evidence").count()>0
    # sidebar navigation to every classic section + V2 pages
    for name in ["Executive Pulse","GTM Workspace","Market Intelligence","SDR Activity","Command Center","Accounts & Prospecting","Content & Collaterals","Leads & Opportunities","Revenue & GP","About"]:
        pg.locator("[data-testid=stSidebar]").get_by_text(name).first.click(); pg.wait_for_timeout(3000)
        ok=pg.locator("[data-testid=stSidebar]").count()==1 and pg.locator("text=Traceback").count()==0 and pg.locator("[data-testid=stException]").count()==0
        out.setdefault("nav",{})[name]=ok
        if name in("Market Intelligence","SDR Activity","Executive Pulse"): pg.screenshot(path=SC+"app_"+name.replace(" ","_")+".png")
    out["fab_on_other_pages"]=pg.locator(".st-key-hoomi_fab3d").count()==1
    out["collapse_button_hidden_desktop"]=pg.locator("[data-testid=stSidebarCollapseButton]").count()==0 or not pg.locator("[data-testid=stSidebarCollapseButton]").first.is_visible()
    # dark mode + phone width
    pg.get_by_text("Dark mode").first.click(); pg.wait_for_timeout(2500); pg.screenshot(path=SC+"app_dark.png")
    pg.set_viewport_size({"width":390,"height":844}); pg.wait_for_timeout(2500); pg.screenshot(path=SC+"app_phone.png")
    out["page_errors"]=errs[:3]
    b.close()
print(json.dumps(out,indent=1))
