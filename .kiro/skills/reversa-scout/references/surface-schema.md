# Schema — .reversa/context/surface.json

Arquivo gerado pelo Scout. Usado pelos demais agentes como fonte de contexto estruturado.

## Estrutura completa

```json
{
  "generated_at": "2026-04-26T10:00:00Z",
  "project_root": "/caminho/do/projeto",
  "languages": [
    { "name": "TypeScript", "extensions": [".ts", ".tsx"], "file_count": 142 },
    { "name": "JavaScript", "extensions": [".js", ".mjs"], "file_count": 23 }
  ],
  "primary_language": "TypeScript",
  "frameworks": [
    { "name": "Next.js", "version": "14.2.0", "source": "package.json" },
    { "name": "Prisma", "version": "5.10.0", "source": "package.json" }
  ],
  "package_manager": "npm",
  "entry_points": [
    { "path": "src/app/layout.tsx", "type": "app_entry" },
    { "path": "src/server.ts", "type": "server_entry" }
  ],
  "config_files": [
    "next.config.js", ".env.example", "tsconfig.json"
  ],
  "ci_cd": [
    ".github/workflows/deploy.yml"
  ],
  "docker": {
    "dockerfile": "Dockerfile",
    "compose": "docker-compose.yml"
  },
  "database_hints": [
    { "path": "prisma/schema.prisma", "type": "prisma_schema" },
    { "path": "prisma/migrations/", "type": "migrations_dir" }
  ],
  "test_framework": "Jest",
  "test_file_count": 47,
  "modules": [
    "auth", "orders", "payments", "users", "notifications"
  ],
  "total_files": 312
}
```

## Campos obrigatórios

`generated_at`, `languages`, `primary_language`, `frameworks`, `entry_points`, `modules`

## Campos opcionais

Todos os demais — inclua apenas o que for encontrado.

## Nota

Use este schema como guia. Se um campo não se aplicar ao projeto, omita-o.
