#!/usr/bin/env bash
# Cria o histórico de commits semânticos do MVP.
# Rode UMA vez, na raiz do projeto, depois de `python manage.py makemigrations core`.
# Os commits usam a SUA identidade do Git (git config user.name / user.email).
set -euo pipefail

cd "$(dirname "$0")/.."

git var GIT_AUTHOR_IDENT >/dev/null 2>&1 || {
  echo "Configure sua identidade antes:"
  echo '  git config --global user.name  "Seu Nome"'
  echo '  git config --global user.email "seu-email@exemplo.com"'
  exit 1
}

if git rev-parse --verify HEAD >/dev/null 2>&1; then
  echo "Este repositório já tem commits. Nada foi feito."
  exit 1
fi

[ -d core/migrations ] || {
  echo "Pasta core/migrations não encontrada. Rode antes: python manage.py makemigrations core"
  exit 1
}

git init -q -b main

# --- main: base do projeto ---------------------------------------------------
git add .gitignore manage.py requirements.txt pytest.ini config core/__init__.py
git commit -q -m "chore: estrutura inicial do projeto Django e dependências"

# --- branch de trabalho (origem do Pull Request) -----------------------------
git switch -q -c feat/mvp-entregas

git add core/models.py core/admin.py core/apps.py core/permissions.py core/migrations
git commit -q -m "feat: modelos de famílias, itens, estoque em lotes e entregas"

git add core/services.py core/forms.py
git commit -q -m "feat: regras de negócio (uma cesta por família/mês, estoque FIFO, alertas e relatório)"

git add core/middleware.py core/context.py core/views.py core/urls.py
git commit -q -m "feat: autenticação, perfis, bloqueio de login e views protegidas"

git add static templates
git commit -q -m "feat: telas acessíveis (login, menu, entrega, estoque, famílias, relatório)"

git add core/management
git commit -q -m "feat: comandos criar_usuario e seed_demo para uso e testes de desempenho"

git add core/tests
git commit -q -m "test: testes unitários das regras e de integração das telas e da segurança"

git add README.md docs scripts
git commit -q -m "docs: README de uso, modelo de Pull Request e script de histórico"

if [ -n "$(git status --porcelain)" ]; then
  echo "ATENÇÃO: sobraram arquivos sem commit:"
  git status --short
  exit 1
fi

echo
git log --oneline --decorate --all
echo
echo "Próximos passos (troque seu-usuario):"
echo "  git remote add origin https://github.com/seu-usuario/maos-solidarias-digital-mvp.git"
echo "  git push -u origin main"
echo "  git push -u origin feat/mvp-entregas"
echo "Depois abra o Pull Request de feat/mvp-entregas para main no GitHub."
