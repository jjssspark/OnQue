'use client';
import { useState } from 'react';

type SummaryResponse = {
  filename: string;
  summary: string;
};

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setSummary(null);
      setErrorMsg('');
    }
  };

  const handleUpload = async () => {
    if (!file) return alert('통화 녹음 파일을 먼저 선택해주세요!');

    const formData = new FormData();
    formData.append('file', file);

    setLoading(true);
    setSummary(null);
    setErrorMsg('');

    try {
      const res = await fetch('http://127.0.0.1:8000/summarize-call', {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) throw new Error('요약 요청 실패');

      const data = await res.json();
      setSummary(data);
    } catch (err: any) {
      setErrorMsg(err.message || '요약 처리 중 오류가 발생했습니다.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 flex items-center justify-center p-6">
      <div className="w-full max-w-3xl bg-white/80 backdrop-blur-lg rounded-2xl shadow-xl p-8 border border-slate-200">
        {/* 헤더 */}
        <h1 className="text-3xl font-bold text-slate-900 mb-2">
          📞 <span className="text-blue-600">OnQue</span> 통화 요약 파일럿
        </h1>
        <p className="text-slate-600 mb-6 text-sm">
          통화 녹음 파일(mp3, m4a, wav)을 업로드하면
          <span className="font-semibold text-emerald-600"> Gemini AI</span>가
          핵심만 자동 요약해드립니다.
        </p>

        {/* 업로드 박스 */}
        <div className="p-5 rounded-xl border border-slate-200 bg-slate-50 mb-6">
          <label className="text-sm font-semibold text-blue-700">
            통화 녹음 파일 선택
          </label>

          <input
            type="file"
            accept=".mp3,.m4a,.wav"
            onChange={handleFileChange}
            className="mt-2 w-full border border-slate-300 rounded-lg p-2 bg-white text-sm cursor-pointer"
          />

          {file && (
            <p className="text-xs mt-2 text-slate-600 bg-white border border-slate-200 px-3 py-1 rounded-md w-fit">
              📎 {file.name}
            </p>
          )}

          <button
            onClick={handleUpload}
            disabled={loading || !file}
            className={`mt-4 w-full py-2 rounded-lg text-sm font-semibold text-white transition 
              ${
                loading || !file
                  ? 'bg-slate-400 cursor-not-allowed'
                  : 'bg-blue-600 hover:bg-blue-700'
              }`}
          >
            {loading ? 'AI 분석 중입니다...' : '요약 시작하기 ✨'}
          </button>

          {errorMsg && (
            <p className="mt-3 text-sm text-red-500">⚠ {errorMsg}</p>
          )}
        </div>

        {/* 결과 */}
        {summary && (
          <div className="p-6 rounded-xl border border-slate-200 bg-white shadow-inner">
            <div className="flex justify-between items-center mb-3">
              <h2 className="text-lg font-bold text-emerald-700">
                📝 요약 리포트
              </h2>
              <span className="text-xs text-slate-400">
                📎 {summary.filename}
              </span>
            </div>

            <hr className="my-4 border-slate-200" />

            <pre className="whitespace-pre-wrap text-sm leading-relaxed text-slate-800">
              {summary.summary}
            </pre>
          </div>
        )}

        {loading && (
          <p className="mt-3 text-xs text-slate-500 text-center">
            ⏳ 통화 길이에 따라 약 10~30초 정도 소요됩니다.
          </p>
        )}
      </div>
    </div>
  );
}
