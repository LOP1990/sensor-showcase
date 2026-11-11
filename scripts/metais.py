#!/usr/bin/env python3
"""
metais.py — registra, uma vez por dia, a cotação de paládio, platina e ouro em EUR por grama no arquivo
metais.json, que o monitor de mercados do app (monitor.html) emenda no histórico da Sensor.

Fontes (sem chave, sem cadastro)
  • gold-api.com: spot em dólares por onça troy (XPD, XPT, XAU).
  • EUR/USD: AwesomeAPI (cotação do momento, até três tentativas); se ela recusar o acesso (acontece a partir dos
    servidores do GitHub, por limite de requisições), taxa de referência do BCE do dia, via Frankfurter.
    Cada registro guarda o EUR/USD usado e de onde ele veio ("fx": "momento" ou "bce").
  EUR/g = USD por onça ÷ EUR/USD ÷ 31,1034768.

O arquivo guarda um registro por dia (data de Brasília). Rodar de novo no mesmo dia substitui o registro do dia.
Um valor fora da faixa plausível, ou a mais de 25 % do registro anterior, é recusado e o script termina com erro
(o arquivo não é alterado), para o problema aparecer na aba Actions em vez de entrar no gráfico.

Uso: python scripts/metais.py metais.json
"""
import datetime as dt, json, os, sys, time, urllib.request

OZ = 31.1034768
TZ = dt.timezone(dt.timedelta(hours=-3))                      # Brasília
UA = {'User-Agent': 'sensor-showcase-metais/1.0 (+https://lop1990.github.io/sensor-showcase/)', 'Accept': 'application/json'}
FAIXA = {'pd': (5, 250), 'pt': (5, 250), 'au': (20, 500)}     # EUR/g: só para barrar leitura absurda


def get(url, timeout=20):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def eurusd(tentativas=3, espera=15):
    for i in range(tentativas):
        try:
            v = float(get('https://economia.awesomeapi.com.br/json/last/EUR-USD')['EURUSD']['bid'])
            if 0.5 < v < 2: return v, 'momento'
        except Exception as e:
            print(f'aviso: AwesomeAPI EUR-USD falhou (tentativa {i + 1} de {tentativas}):', e)
        if i + 1 < tentativas: time.sleep(espera)
    v = float(get('https://api.frankfurter.dev/v1/latest?base=EUR&symbols=USD')['rates']['USD'])
    if not 0.5 < v < 2: raise SystemExit(f'EUR/USD fora da faixa: {v}')
    return v, 'bce'


def main(path):
    fx, fx_src = eurusd()
    hoje = dt.datetime.now(TZ).date().isoformat()
    reg = {'d': hoje}
    for sym, key in (('XPD', 'pd'), ('XPT', 'pt'), ('XAU', 'au')):
        usd = float(get(f'https://api.gold-api.com/price/{sym}')['price'])
        v = round(usd / fx / OZ, 2); lo, hi = FAIXA[key]
        if not lo < v < hi: raise SystemExit(f'{sym}: {v} EUR/g fora da faixa plausível ({lo}–{hi})')
        reg[key] = v
    reg['eurusd'] = round(fx, 4); reg['fx'] = fx_src

    doc = {'dias': []}
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f: doc.update(json.load(f))
    doc['unidade'] = 'EUR/g'
    doc['fonte'] = 'gold-api.com (spot, USD por onça troy) convertido pelo EUR/USD de cada registro: fx "momento" = cotação do momento (AwesomeAPI); fx "bce" = taxa de referência do BCE do dia (Frankfurter)'
    doc.pop('cambio', None)
    todos = doc.get('dias', [])
    dias = [x for x in todos if x.get('d') != hoje]
    if todos:
        ant = max(todos, key=lambda x: x['d'])                # o registro mais recente, inclusive o de hoje, se já houver
        for key in ('pd', 'pt', 'au'):
            if ant.get(key) and abs(reg[key] / ant[key] - 1) > 0.25:
                raise SystemExit(f'{key}: {reg[key]} está a mais de 25 % do registro de {ant["d"]} ({ant[key]}); nada foi gravado')
    dias.append(reg); dias.sort(key=lambda x: x['d'])
    doc['dias'] = dias
    doc['atualizado'] = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    # um registro por linha, para o histórico do git ficar legível
    linhas = ',\n'.join('    ' + json.dumps(x, ensure_ascii=False, separators=(', ', ': ')) for x in dias)
    cab = {k: v for k, v in doc.items() if k != 'dias'}
    txt = '{\n' + ''.join(f'  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)},\n' for k, v in cab.items()) + '  "dias": [\n' + linhas + '\n  ]\n}\n'
    json.loads(txt)                                           # confere antes de gravar
    with open(path, 'w', encoding='utf-8') as f: f.write(txt)
    print(f'{hoje}: Pd {reg["pd"]} · Pt {reg["pt"]} · Au {reg["au"]} EUR/g (EUR/USD {reg["eurusd"]}, fx {fx_src}) — {len(dias)} dia(s) no arquivo')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'metais.json')
