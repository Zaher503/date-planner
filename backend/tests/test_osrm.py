import httpx
import pytest

from app.plan import osrm

HOME = (34.0461, -118.3265)
PERCH = (34.0488, -118.2518)


def client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_route_parses_osrm():
    seen = {}

    def handler(req: httpx.Request):
        seen["url"] = str(req.url)
        return httpx.Response(200, json={"code": "Ok", "routes": [{"duration": 900.0, "distance": 8200.0}]})

    leg = osrm.route(HOME, PERCH, "drive", client=client(handler))
    assert leg.minutes == 15 and leg.metres == 8200 and not leg.estimated
    assert "osrm-car" in seen["url"] and "/route/v1/driving/-118.326500,34.046100;-118.251800,34.048800" in seen["url"]


def test_walk_uses_foot_server():
    seen = {}

    def handler(req):
        seen["url"] = str(req.url)
        return httpx.Response(200, json={"code": "Ok", "routes": [{"duration": 600, "distance": 800}]})

    osrm.route(HOME, PERCH, "walk", client=client(handler))
    assert "osrm-foot" in seen["url"] and "/route/v1/foot/" in seen["url"]


def test_route_falls_back_when_down():
    def handler(req):
        raise httpx.ConnectError("refused")

    leg = osrm.route(HOME, PERCH, "drive", client=client(handler))
    assert leg.estimated
    km = osrm.haversine_m(HOME, PERCH) / 1000
    assert 6.5 < km < 7.5
    assert leg.minutes == pytest.approx(km / 30 * 60)


def test_walk_fallback_speed():
    def handler(req):
        return httpx.Response(500)

    leg = osrm.route(HOME, PERCH, "walk", client=client(handler))
    assert leg.estimated and leg.minutes == pytest.approx(leg.metres / 1000 / 4.8 * 60)


def test_no_route_code_falls_back():
    def handler(req):
        return httpx.Response(200, json={"code": "NoRoute", "routes": []})

    assert osrm.route(HOME, PERCH, client=client(handler)).estimated


def test_table_one_to_many_with_null_entry():
    far = (34.2, -118.5)

    def handler(req):
        assert req.url.params["sources"] == "0" and req.url.params["destinations"] == "1;2"
        return httpx.Response(200, json={"code": "Ok", "durations": [[300.0, None]], "distances": [[2500.0, None]]})

    legs = osrm.table(HOME, [PERCH, far], "drive", client=client(handler))
    assert legs[0].minutes == 5 and legs[0].metres == 2500 and not legs[0].estimated
    assert legs[1].estimated and legs[1].metres > 10000


def test_table_falls_back_when_down():
    def handler(req):
        raise httpx.ReadTimeout("slow")

    legs = osrm.table(HOME, [PERCH, HOME], "walk", client=client(handler))
    assert all(leg.estimated for leg in legs)
    assert legs[1].minutes == 0
    assert osrm.table(HOME, [], client=client(handler)) == []


def test_unknown_mode():
    with pytest.raises(ValueError):
        osrm.route(HOME, PERCH, "bike")
