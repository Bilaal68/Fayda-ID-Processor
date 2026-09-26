import React, { useState } from 'react';
import Navbar from './components/Navbar';
import PdfSlotUploader from './components/PdfSlotUploader';
import PdfViewer from './components/PdfViewer';
import { processPdfTemplate } from './services/api';
import { AlertCircle } from 'lucide-react';

export default function App() {
  const [files, setFiles] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [generatedPdf, setGeneratedPdf] = useState(null);

  const handleGenerate = async () => {
    if (files.length === 0) return;
    setIsLoading(true);
    setError(null);

    try {
      const result = await processPdfTemplate(files);
      setGeneratedPdf(result);
    } catch (err) {
      setError(err.message || 'An unexpected error occurred while generating the PDF.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleReset = () => {
    if (generatedPdf?.blobUrl) {
      URL.revokeObjectURL(generatedPdf.blobUrl);
    }
    setGeneratedPdf(null);
    setError(null);
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col selection:bg-indigo-500 selection:text-white">
      <Navbar />

      <main className="flex-1 flex items-center justify-center px-4 sm:px-6 lg:px-8 py-8">
        <div className="w-full max-w-4xl space-y-4">

          {/* Error Banner */}
          {error && (
            <div className="p-4 rounded-2xl bg-rose-500/10 border border-rose-500/30 text-rose-300 flex items-start gap-3 shadow-lg">
              <AlertCircle className="w-5 h-5 shrink-0 text-rose-400 mt-0.5" />
              <div className="flex-1">
                <h4 className="text-sm font-semibold text-rose-200">Processing Error</h4>
                <p className="text-xs text-rose-300/90 mt-0.5">{error}</p>
              </div>
              <button
                onClick={() => setError(null)}
                className="text-xs text-rose-400 hover:text-rose-200 cursor-pointer font-medium px-2 py-1 rounded-lg hover:bg-rose-500/20"
              >
                Dismiss
              </button>
            </div>
          )}

          {generatedPdf ? (
            /* Preview Mode */
            <PdfViewer
              blobUrl={generatedPdf.blobUrl}
              filename={generatedPdf.filename}
              onReset={handleReset}
            />
          ) : (
            /* Upload Mode — clean, no header, no cards */
            <div className="bg-slate-900/70 border border-slate-800 rounded-3xl p-6 sm:p-8 shadow-xl backdrop-blur-sm">
              <PdfSlotUploader
                files={files}
                setFiles={setFiles}
                onGenerate={handleGenerate}
                isLoading={isLoading}
              />
            </div>
          )}

        </div>
      </main>
    </div>
  );
}
