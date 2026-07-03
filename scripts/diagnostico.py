from datetime import date

from financeiro.context import current_user_id
from financeiro.conn import get_conn
from financeiro.db import resumo_por_categoria, recategorizar_movimentos

token = current_user_id.set("marcos")
try:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM movimentos").fetchone()["n"]
        print("total movimentos:", total)

        rows = conn.execute(
            """
            SELECT categoria, COUNT(*) AS n,
                   SUM(COALESCE(credito, 0)) AS c,
                   SUM(COALESCE(debito, 0)) AS d
            FROM movimentos
            GROUP BY categoria
            ORDER BY d DESC NULLS LAST
            """
        ).fetchall()
        print("\n=== categorias no banco ===")
        for r in rows:
            print(f"  {r['categoria']}: {r['n']} movs, credito={r['c']}, debito={r['d']}")

        gas = conn.execute(
            """
            SELECT categoria, COUNT(*) AS n FROM movimentos
            WHERE UPPER(historico) LIKE '%POSTO%'
               OR UPPER(historico) LIKE '%COMBUST%'
            GROUP BY categoria
            """
        ).fetchall()
        print("\n=== posto/combust por categoria ===")
        for r in gas:
            print(f"  {r['categoria']}: {r['n']}")

        mi = conn.execute("SELECT MIN(data) AS mi, MAX(data) AS ma FROM movimentos").fetchone()
        print("\nintervalo datas:", mi["mi"], "->", mi["ma"])

    n = recategorizar_movimentos()
    print("\nrecategorizados:", n)

    res = resumo_por_categoria(date(2026, 5, 1), date(2026, 5, 31))
    print("\n=== resumo maio/2026 ===")
    for cat, c, d in res:
        if d > 0 or c > 0:
            print(f"  {cat}: entrada={c} saida={d}")

    gas_res = [x for x in res if x[0] == "Gasolina"]
    print("\nGasolina no resumo:", gas_res)
finally:
    current_user_id.reset(token)
