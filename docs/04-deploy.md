# Deploy em produção — vitrinecps.com.br

Infra da ADR-006: VPS Hostinger com Coolify, atrás de Cloudflare Tunnel.
Banco no Neon, imagens no Cloudflare R2. Domínio registrado no Registro.br.

Host canônico: **https://vitrinecps.com.br** (o `www` redireciona).

## Arquivos

- `Dockerfile` — imagem de produção; `collectstatic` no build (whitenoise).
- `docker/start.sh` — `migrate` + `createcachetable` + gunicorn na porta 8000.
- `.dockerignore`

## 1. Zona no Cloudflare

1. Cloudflare → Add a site → `vitrinecps.com.br` → plano Free.
2. Pular a importação de registros (a zona nasce vazia; o túnel cria os dele).
3. Anotar os dois nameservers que o Cloudflare indicar.

A zona no Cloudflare é obrigatória por dois motivos: domínio próprio no R2
(ADR-006 proíbe `*.r2.dev`) e os hostnames do túnel.

## 2. Nameservers no Registro.br

1. registro.br → painel do domínio → **Alterar servidores DNS** → informar os
   dois NS do Cloudflare.
2. **DNSSEC**: o DNS automático do Registro.br vem com DNSSEC ativo. Ao trocar
   para NS externos, conferir que o DS foi removido — DS antigo com zona nova
   derruba o domínio para quem valida DNSSEC. (Dá para reativar depois com o
   DS do Cloudflare, opcional.)
3. Propagação: o Registro.br publica em até ~1h. A zona fica "Active" no
   painel do Cloudflare quando concluir.

## 3. Hostnames no túnel

Zero Trust → Networks → Tunnels → túnel existente → Public Hostname:

| Hostname | Service |
|---|---|
| `vitrinecps.com.br` | o mesmo service/porta dos apps que já estão no túnel |
| `www.vitrinecps.com.br` | idem |

Cada hostname cria o CNAME proxied na zona automaticamente. Usar exatamente a
mesma configuração de service dos apps que já funcionam (inclusive
`noTLSVerify`/`originServerName`, se for o caso) — é isso que garante o
`X-Forwarded-Proto: https` que o Django espera (`SECURE_PROXY_SSL_HEADER`).

## 4. App no Coolify

Novo recurso → repositório `guilhermepama/vitrine-cps`, branch `main`,
build pack **Dockerfile**.

- **Domains**: `https://vitrinecps.com.br,https://www.vitrinecps.com.br`,
  com redirecionamento para o domínio sem `www` (opção "Direction").
- **Ports Exposes**: `8000`.
- **Healthcheck**: HTTP GET, path `/saude/`, porta 8000, expected 200,
  start period 30 s (o primeiro boot roda as migrações).

### Variáveis de ambiente

| Variável | Valor / como gerar |
|---|---|
| `DJANGO_DEBUG` | `0` |
| `DJANGO_SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `DJANGO_ALLOWED_HOSTS` | `vitrinecps.com.br,www.vitrinecps.com.br,localhost` (o `localhost` é do healthcheck do Coolify, que testa de dentro do container) |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://vitrinecps.com.br,https://www.vitrinecps.com.br` |
| `DJANGO_URL_PUBLICA` | `https://vitrinecps.com.br` |
| `DJANGO_SECURE_SSL_REDIRECT` | `0` (o Cloudflare já redireciona HTTP→HTTPS na borda) |
| `DJANGO_IP_HEADER` | `CF-Connecting-IP` — ver nota abaixo |
| `DATABASE_URL` | connection string do Neon, projeto de produção `vitrine-cps` (`?sslmode=require`) |
| `RA_HMAC_SECRET` | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `QR_HMAC_SECRET` | `openssl rand -hex 32` |
| `IP_HMAC_SECRET` | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `R2_ACCOUNT_ID` | painel do Cloudflare (lateral direita da página do R2) |
| `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` | token de API do R2 restrito ao bucket (Object Read & Write) |
| `R2_BUCKET` | `vitrine-cps` |
| `R2_PUBLIC_DOMAIN` | `media.vitrinecps.com.br` |

Os três segredos HMAC são distintos entre si e distintos da SECRET_KEY —
gerar quatro valores diferentes.

> **`CF-Connecting-IP`, não `X-Real-Ip`** (corrige a ADR-006): atrás do
> túnel, o Traefik enxerga todas as requisições com o IP do cloudflared.
> Com `X-Real-Ip`, o público inteiro do evento viraria um IP só e o rate
> limit (300/10 min/IP) barraria a votação. O `CF-Connecting-IP` é escrito
> pelo Cloudflare e, com o firewall fechado (só o túnel entra), o cliente
> não consegue forjá-lo.

## 5. R2 (imagens)

1. R2 → Create bucket → `vitrine-cps` (região automática).
2. Bucket → Settings → **Custom Domains** → `media.vitrinecps.com.br`
   (exige a zona ativa no Cloudflare — passo 1).
3. R2 → Manage API tokens → token **Object Read & Write** restrito a este
   bucket → copiar Access Key ID e Secret.

## 6. Primeiro deploy e verificação

1. Deploy no Coolify; o `start.sh` roda `migrate` e `createcachetable`.
2. Superusuário: terminal do container no Coolify →
   `python manage.py createsuperuser`.
3. Checklist:
   - [ ] `https://vitrinecps.com.br/saude/` responde 200
   - [ ] `http://` redireciona para `https://`; `www` redireciona para o apex
   - [ ] Login no `/admin/` funciona (exercita CSRF + cookies Secure —
         se falhar com erro de CSRF, o `X-Forwarded-Proto` não está
         chegando como `https`; rever o service do túnel, passo 3)
   - [ ] CSS carregando (whitenoise/manifest ok)
   - [ ] Upload de imagem num projeto → URL servida em
         `media.vitrinecps.com.br` e prévia abrindo
   - [ ] IP real: acessar de 4G e de Wi-Fi e conferir no rate limit/logs que
         são IPs distintos (não pode aparecer IP interno do Docker)

## Operação

- Deploy = push na `main` (configurar webhook/auto-deploy no Coolify) ou
  botão Deploy.
- Logs: Coolify → aplicação → Logs (o Django loga no console; rotas do
  visitante filtradas — guardrail 11).
- Backup do banco: responsabilidade do Neon (point-in-time restore).
