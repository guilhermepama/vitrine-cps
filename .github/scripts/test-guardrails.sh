#!/usr/bin/env bash
# Testes do verificador de guardrails: cada caso monta um repo temporário
# com um arquivo e confere se o script barra (1) ou deixa passar (0).
# Roda no CI para que ninguém afrouxe o verificador sem perceber.

set -uo pipefail
SCRIPT="$(cd "$(dirname "$0")" && pwd)/guardrails.sh"
FALHAS=0
TOTAL=0

caso() {  # $1 descrição | $2 esperado (0/1) | $3 caminho | $4 conteúdo
  TOTAL=$((TOTAL + 1))
  local dir; dir=$(mktemp -d)
  ( cd "$dir" && git init -q && mkdir -p "$(dirname "$3")" && printf '%s\n' "$4" > "$3" && git add -A )
  bash "$SCRIPT" "$dir" > "$dir.log" 2>&1
  local obtido=$?
  if [ "$obtido" -eq "$2" ]; then
    echo "ok   - $1"
  else
    echo "FALHA- $1 (esperado $2, obtido $obtido)"; sed 's/^/       /' "$dir.log"
    FALHAS=$((FALHAS + 1))
  fi
  rm -rf "$dir" "$dir.log"
}

# Deve passar
caso "repo só com docs passa"                     0 docs/x.md        "CPF é proibido. SELECT \${x}"
caso "query parametrizada JS passa"               0 src/votos.js     "db.query('INSERT INTO votos (token_id, projeto_id) VALUES (\$1, \$2)', [t, p])"
caso "query parametrizada Python passa"           0 app/votos.py     "cur.execute(\"SELECT id FROM tokens WHERE id = %s\", (token,))"
caso "segredo lido do ambiente passa"             0 src/qr.js        "const QR_HMAC_SECRET = process.env.QR_HMAC_SECRET"
caso "tabela visitantes correta passa"            0 db/001.sql       "CREATE TABLE visitantes (id serial, nome text, email text, telefone text, consentimento_em timestamptz);"
caso ".env.example passa"                         0 .env.example     "QR_HMAC_SECRET="

# Deve barrar
caso "G3: .env commitado"                         1 .env             "X=1"
caso "G3: .env.local commitado"                   1 .env.local       "X=1"
caso "G3: segredo fixo no código"                 1 src/qr.js        "const QR_HMAC_SECRET = 'xxxxxxxxxxxxxxxx'"
caso "G6: coluna token em visitantes (SQL)"       1 db/002.sql       "CREATE TABLE visitantes (
  id serial,
  token_id uuid REFERENCES tokens(id)
);"
caso "G6: vínculo no código"                      1 src/cadastro.ts  "await save({ ...dados, visitante_token_id: token })"
caso "G9: campo CPF"                              1 src/form.ts      "const cpf = body.cpf"
caso "G9: data de nascimento"                     1 app/models.py    "data_nascimento = models.DateField()"
caso "G13: template literal com SQL"              1 src/votos.js     "db.query(\`SELECT * FROM votos WHERE token_id = '\${token}'\`)"
caso "G13: f-string com SQL"                      1 app/votos.py     "cur.execute(f\"SELECT * FROM votos WHERE token_id = '{token}'\")"
caso "G13: concatenação com SQL"                  1 src/votos.js     "db.query(\"DELETE FROM votos WHERE id = \" + id)"
caso "G13: concatenação PHP"                      1 src/votos.php    "\$sql = \"SELECT * FROM votos WHERE id = \" . \$id;"

echo
echo "$((TOTAL - FALHAS))/$TOTAL casos ok"
[ "$FALHAS" -eq 0 ]
