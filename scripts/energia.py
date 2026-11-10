#!/usr/bin/env python3
"""
energia.py — gera o energia.json que o app da Sensor lê na aba Ambiental.

Fontes
  • SolisCloud (usina fotovoltaica): potência agora, energia do dia/mês/ano/total e a curva do dia.
  • Medidor de consumo (opcional): qualquer endpoint JSON com a potência ativa da fábrica.

Variáveis de ambiente
  SOLIS_KEY_ID, SOLIS_KEY_SECRET   chave da API SolisCloud (as mesmas do EnergiaMonitor)
  SOLIS_STATION_ID                 id da usina na SolisCloud (opcional: usa a 1ª usina da conta)
  LOAD_URL                         opcional — URL que devolve JSON com a potência consumida agora
  LOAD_KEYS                        opcional — chaves (separadas por vírgula) a somar em W; padrão:
                                   potencia_ativa_fase_a,potencia_ativa_fase_b,potencia_ativa_fase_c
  TZ_OFFSET                        fuso da usina em horas (padrão -3 = Brasília)

Sem SOLIS_KEY_ID/SECRET o script termina com código 0 sem escrever nada — o app continua simulando.
Uso: python scripts/energia.py energia.json
"""
import base64, datetime as dt, hashlib, hmac, json, os, sys, urllib.request

BASE = 'https://www.soliscloud.com:13333'
TZ = dt.timezone(dt.timedelta(hours=float(os.environ.get('TZ_OFFSET', '-3'))))


def solis(path, body):
    key_id = os.environ['SOLIS_KEY_ID']; secret = os.environ['SOLIS_KEY_SECRET'].encode()
    data = json.dumps(body, separators=(',', ':')).encode()
    md5 = base64.b64encode(hashlib.md5(data).digest()).decode()
    date = dt.datetime.now(dt.timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')
    sign_src = f'POST\n{md5}\napplication/json\n{date}\n{path}'
    sign = base64.b64encode(hmac.new(secret, sign_src.encode(), hashlib.sha1).digest()).decode()
    req = urllib.request.Request(BASE + path, data=data, method='POST', headers={
        'Content-MD5': md5, 'Content-Type': 'application/json', 'Date': date, 'Authorization': f'API {key_id}:{sign}'})
    with urllib.request.urlopen(req, timeout=40) as r:
        j = json.loads(r.read().decode('utf-8'))
    if str(j.get('code', '0')) not in ('0', '200') or j.get('success') is False:
        raise RuntimeError(f'SolisCloud {path}: {j.get("code")} {j.get("msg")}')
    return j.get('data')


def num(v):
    try: return float(v)
    except (TypeError, ValueError): return None


def kw(value, unit):
    """Converte potência para kW a partir da unidade informada pela API (W, kW, MW)."""
    v = num(value)
    if v is None: return None
    u = (unit or 'kW').strip().lower()
    return v / 1000 if u == 'w' else v * 1000 if u == 'mw' else v


def kwh(value, unit):
    v = num(value)
    if v is None: return None
    u = (unit or 'kWh').strip().lower()
    return v / 1000 if u == 'wh' else v * 1000 if u == 'mwh' else v * 1e6 if u == 'gwh' else v


def station():
    sid = os.environ.get('SOLIS_STATION_ID', '').strip()
    recs = (solis('/v1/api/userStationList', {'pageNo': 1, 'pageSize': 20}) or {}).get('page', {}).get('records', [])
    if not recs: raise RuntimeError('nenhuma usina na conta SolisCloud')
    rec = next((r for r in recs if str(r.get('id')) == sid), None) if sid else recs[0]
    if rec is None: raise RuntimeError(f'usina {sid} não encontrada; disponíveis: {[(r.get("id"), r.get("stationName")) for r in recs]}')
    return rec


def day_curve(sid, day):
    rows = solis('/v1/api/stationDay', {'id': sid, 'money': 'BRL', 'time': day.strftime('%Y-%m-%d'), 'timeZone': int(TZ.utcoffset(None).total_seconds() // 3600)}) or []
    out = []
    for r in rows:
        p = kw(r.get('power'), r.get('powerStr'))
        t = r.get('timeStr') or r.get('time')
        if p is None or t is None: continue
        if isinstance(t, (int, float)) or str(t).isdigit():
            hhmm = dt.datetime.fromtimestamp(int(t) / 1000, TZ).strftime('%H:%M')
        else:
            hhmm = str(t)[-8:-3] if len(str(t)) >= 16 else str(t)[:5]
        out.append({'t': hhmm, 'pv': round(p, 2)})
    return out


def load_now():
    url = os.environ.get('LOAD_URL', '').strip()
    if not url: return None
    keys = [k.strip() for k in os.environ.get('LOAD_KEYS', 'potencia_ativa_fase_a,potencia_ativa_fase_b,potencia_ativa_fase_c').split(',') if k.strip()]
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={'Accept': 'application/json'}), timeout=30) as r:
            j = json.loads(r.read().decode('utf-8'))
        if isinstance(j, list) and j: j = j[-1]
        total = 0.0; found = False
        for k in keys:
            v = num(j.get(k)) if isinstance(j, dict) else None
            if v is not None: total += v; found = True
        return round(total / 1000, 2) if found else None     # W → kW
    except Exception as e:                                      # consumo é opcional: não derruba a geração
        print(f'aviso: consumo indisponível ({e})', file=sys.stderr)
        return None


def main(out_path):
    if not os.environ.get('SOLIS_KEY_ID') or not os.environ.get('SOLIS_KEY_SECRET'):
        print('SOLIS_KEY_ID/SOLIS_KEY_SECRET ausentes — nada a fazer (o app segue em simulação).'); return 0
    now = dt.datetime.now(TZ)
    rec = station()
    sid = str(rec.get('id'))
    data = {
        'source': 'soliscloud',
        'updated': now.isoformat(timespec='seconds'),
        'station': {'id': sid, 'name': rec.get('stationName'), 'capacity_kwp': kw(rec.get('capacity'), rec.get('capacityStr') or 'kW')},
        'now': {'pv_kw': kw(rec.get('power'), rec.get('powerStr')), 'load_kw': load_now()},
        'today': {'pv_kwh': kwh(rec.get('dayEnergy'), rec.get('dayEnergyStr'))},
        'month': {'pv_kwh': kwh(rec.get('monthEnergy'), rec.get('monthEnergyStr'))},
        'year': {'pv_kwh': kwh(rec.get('yearEnergy'), rec.get('yearEnergyStr'))},
        'lifetime': {'pv_kwh': kwh(rec.get('allEnergy'), rec.get('allEnergyStr'))},
        'curve': [],
    }
    try:
        data['curve'] = day_curve(sid, now)
    except Exception as e:
        print(f'aviso: curva do dia indisponível ({e})', file=sys.stderr)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f'{out_path}: {data["station"]["name"]} — agora {data["now"]["pv_kw"]} kW, hoje {data["today"]["pv_kwh"]} kWh, total {data["lifetime"]["pv_kwh"]} kWh, {len(data["curve"])} pontos')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else 'energia.json'))
