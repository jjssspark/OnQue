export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000';

export type SummaryResponse = {
  filename: string;
  summary: string;
};

async function postFile(path: string, file: File): Promise<SummaryResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail || '요약 요청이 실패했습니다.');
  }

  return res.json();
}

export function summarizeCall(file: File): Promise<SummaryResponse> {
  return postFile('/summarize-call', file);
}

export function summarizeDocument(file: File): Promise<SummaryResponse> {
  return postFile('/summarize-document', file);
}
