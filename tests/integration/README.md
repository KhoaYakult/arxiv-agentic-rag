# Integration test (cần Postgres + pgvector thật)

Chạy trên 1 Postgres **riêng để test**, không phải Supabase. Không đặt `TEST_DATABASE_URL`
thì cả thư mục này tự skip (nên `make test` vẫn chạy được không cần DB).

```bash
docker run -d --rm --name pgtest -e POSTGRES_PASSWORD=postgres -p 55432:5432 pgvector/pgvector:pg16
make test-integration
docker stop pgtest
```

- Test tự dựng DB giống Supabase (pgvector nằm ở schema `extensions`) rồi chạy `db/schema.sql`.
- Test **TRUNCATE bảng**, nên `conftest.py` từ chối chạy nếu URL chứa "supabase".
- CI (`.github/workflows/ci.yml`) dùng service container `pgvector/pgvector:pg16` cho các test này.
