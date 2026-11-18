"""One-time setup endpoint for hosted environments where the database is only reachable from the server
(e.g. Vercel + Neon with sensitive credentials).

Disabled unless NACB_OPS_TOKEN is set. Call with POST and header  X-Ops-Token: <token>, e.g.
    curl -X POST -H "X-Ops-Token: ..." https://<site>/ops/setup/?step=migrate
Remove NACB_OPS_TOKEN afterwards to switch the endpoint off."""
import hmac
import io
import os

from django.core.management import call_command
from django.http import Http404, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

STEPS = {
    "migrate": [("migrate", ["--noinput"])],
    "cache": [("createcachetable", [])],
    "seed": [("seed_demo", ["--demo-users"]), ("seed_demo_round", []), ("seed_past_events", []), ("seed_partnerships", [])],
    "check": [("showmigrations", ["--plan"])],
}


@csrf_exempt
@require_POST
def setup(request):
    token = os.environ.get("NACB_OPS_TOKEN", "")
    given = request.headers.get("X-Ops-Token", "")
    if len(token) < 32 or not hmac.compare_digest(token, given):
        raise Http404  # endpoint does not exist unless correctly enabled
    step = request.GET.get("step", "")
    if step == "rotate_demo":
        return rotate_demo()
    if step not in STEPS:
        return JsonResponse({"error": "unknown step", "steps": list(STEPS)}, status=400)
    out = io.StringIO()
    try:
        for name, args in STEPS[step]:
            call_command(name, *args, stdout=out, stderr=out)
    except Exception as exc:  # report, never expose settings
        return JsonResponse({"step": step, "ok": False, "error": f"{type(exc).__name__}: {exc}", "log": out.getvalue()[-3000:]}, status=500)
    log = out.getvalue()
    if step == "check":
        log = f"applied: {log.count('[X]')}, pending: {log.count('[ ]')}"
    return JsonResponse({"step": step, "ok": True, "log": log[-3000:]})


def rotate_demo():
    """Give every demo account (@nacb.test) the password held in NACB_DEMO_PASSWORD. Real accounts are untouched."""
    from accounts.models import User
    from portal.demo_credentials import demo_password
    if not os.environ.get("NACB_DEMO_PASSWORD"):
        return JsonResponse({"step": "rotate_demo", "ok": False, "error": "NACB_DEMO_PASSWORD is not set"}, status=400)
    pw, n = demo_password(), 0
    for u in User.objects.filter(email__endswith="@nacb.test"):
        u.set_password(pw)
        u.save(update_fields=["password"])
        n += 1
    return JsonResponse({"step": "rotate_demo", "ok": True, "log": f"{n} demo accounts updated"})
