-- 초기 스키마: todos, schedules, documents, chat_messages
-- 참고용 문서. 실제 적용은 애플리케이션 기동 시 SQLAlchemy Base.metadata.create_all()이 수행한다.

-- up
CREATE TABLE todos (
  id BIGSERIAL PRIMARY KEY,
  content TEXT NOT NULL,
  due_date DATE NULL,
  is_done BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE schedules (
  id BIGSERIAL PRIMARY KEY,
  title TEXT NOT NULL,
  scheduled_date DATE NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE documents (
  id BIGSERIAL PRIMARY KEY,
  source_type TEXT NOT NULL CHECK (source_type IN ('call', 'document')),
  category TEXT NOT NULL CHECK (category IN ('기획', '디자인', '개발', '마케팅', '기타', '통화')),
  filename TEXT NOT NULL,
  summary TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE chat_messages (
  id BIGSERIAL PRIMARY KEY,
  sender TEXT NOT NULL,
  content TEXT NOT NULL,
  is_bot BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- down
-- DROP TABLE chat_messages;
-- DROP TABLE documents;
-- DROP TABLE schedules;
-- DROP TABLE todos;
