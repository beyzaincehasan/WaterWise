"""Endpoint testleri ve doğrulama betiği."""
import json
import urllib.request
import urllib.error

BASE_URL = "http://127.0.0.1:8000"

def make_request(method, path, data=None):
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"}
    req_data = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = body
        return e.code, parsed

def run_tests():
    tests = []

    # 1. Health
    status, res = make_request("GET", "/health")
    tests.append({
        "endpoint": "GET /health",
        "status_code": status,
        "detail": f"Status: {res.get('status')}, Model: {res.get('model_version')}, Daireler: {res.get('known_apartments_count')}"
    })

    # 2. Apartments List
    status, res = make_request("GET", "/api/v1/apartments")
    tests.append({
        "endpoint": "GET /api/v1/apartments",
        "status_code": status,
        "detail": f"{len(res)} daire listelendi. İlk: {res[0]['id']} (Ort: {res[0]['normal_daily_mean_liters']} L)"
    })

    # 3. Single Apartment
    status, res = make_request("GET", "/api/v1/apartments/APT_011")
    tests.append({
        "endpoint": "GET /api/v1/apartments/APT_011",
        "status_code": status,
        "detail": f"Daire: {res.get('id')}, Küme: {res.get('cluster_name')}, Ort: {res.get('normal_daily_mean_liters')} L"
    })

    # 4. Daily Consumption
    status, res = make_request("GET", "/api/v1/apartments/APT_011/daily-consumption?start_date=2022-11-01&end_date=2022-11-20")
    tests.append({
        "endpoint": "GET /api/v1/apartments/APT_011/daily-consumption",
        "status_code": status,
        "detail": f"{len(res)} gün döndü. Örnek: {res[0]['date']} -> {res[0]['total_liters']} L (Soğuk: {res[0]['cold_water_liters']} L, Sıcak: {res[0]['hot_water_liters']} L)"
    })

    # 5. Fixture Breakdown
    status, res = make_request("GET", "/api/v1/apartments/APT_011/fixture-breakdown")
    tests.append({
        "endpoint": "GET /api/v1/apartments/APT_011/fixture-breakdown",
        "status_code": status,
        "detail": f"{len(res)} kategori: " + ", ".join([f"{f['fixture']}: %{f['percentage']}" for f in res])
    })

    # 6. Apartment Stats
    status, res = make_request("GET", "/api/v1/apartments/APT_011/stats")
    tests.append({
        "endpoint": "GET /api/v1/apartments/APT_011/stats",
        "status_code": status,
        "detail": f"Toplam: {res.get('total_consumption_liters')} L, Günlük Ort: {res.get('daily_mean_liters')} L, Gece Oranı: %{res.get('night_consumption_ratio')}"
    })

    # 7. Evaluate Range (Dashboard son 24 saat)
    status, res = make_request("GET", "/api/v1/apartments/APT_011/evaluate-range?start_time=2022-11-23T00:00:00Z&end_time=2022-11-23T12:00:00Z")
    tests.append({
        "endpoint": "GET /api/v1/apartments/APT_011/evaluate-range",
        "status_code": status,
        "detail": f"{len(res)} saat değerlendirildi. İlk saat: {res[0]['timestamp_local']} -> Durum: {res[0]['status']}, Skor: {res[0]['anomaly_score']}"
    })

    # 8. Anomaly Detect - Normal Saat Testi
    normal_req = {
        "apartment_id": "APT_011",
        "target_timestamp": "2022-11-23T10:00:00Z",
        "history_days": 28,
        "save_log": True
    }
    status, res = make_request("POST", "/api/v1/anomalies/detect", normal_req)
    tests.append({
        "endpoint": "POST /api/v1/anomalies/detect (Normal Saat)",
        "status_code": status,
        "detail": f"Durum: {res.get('status')} | Skor: {res.get('anomaly_score')} | Tüketim: {res.get('consumption_liters')} L | Mesaj: {res.get('message')}"
    })

    # 9. Simulate Demo (Gece sürekli akış kaçağı enjeksiyonu)
    demo_req = {
        "apartment_id": "APT_011",
        "start_time": "2022-11-24 01:00",
        "hours": 3.0,
        "rate_l_per_hour": 18.0
    }
    status, res = make_request("POST", "/api/v1/anomalies/simulate-demo", demo_req)
    leak_statuses = [f"{r['timestamp_local'][11:16]}: {r['status']} ({r['anomaly_score']})" for r in res.get("results", [])]
    tests.append({
        "endpoint": "POST /api/v1/anomalies/simulate-demo",
        "status_code": status,
        "detail": f"{res.get('simulated_hours')} saat simüle edildi. Saatler: " + ", ".join(leak_statuses)
    })

    # 10. List Anomaly Logs
    status, res = make_request("GET", "/api/v1/anomalies?apartment_id=APT_011")
    tests.append({
        "endpoint": "GET /api/v1/anomalies",
        "status_code": status,
        "detail": f"Toplam {len(res)} anomali kaydı bulundu. Son anomali durumu: {res[0]['status']}, Skor: {res[0]['anomaly_score']}"
    })

    print(json.dumps(tests, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    run_tests()

