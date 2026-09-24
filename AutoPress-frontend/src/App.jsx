import React, { useState } from 'react';
import Navbar from './components/Navbar';
import PdfSlotUploader from './components/PdfSlotUploader';
import PdfViewer from './components/PdfViewer';
import { processPdfTemplate } from './services/api';
import { AlertCircle, FileCheck, Layers, Cpu, ShieldCheck } from 'lucide-react';

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

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Error Banner */}
        {error && (
          <div className="mb-6 p-4 rounded-2xl bg-rose-500/10 border border-rose-500/30 text-rose-300 flex items-start gap-3 shadow-lg">
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
          <div className="space-y-4 animate-in fade-in duration-300">
            <PdfViewer
              blobUrl={generatedPdf.blobUrl}
              filename={generatedPdf.filename}
              onReset={handleReset}
            />
          </div>
        ) : (
          /* Upload / Configuration Mode */
          <div className="space-y-8">
            {/* Hero Header */}
            <div className="text-center max-w-2xl mx-auto space-y-3">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-xs font-medium">
                <FileCheck className="w-3.5 h-3.5" />
                <span>Template PDF Pipeline</span>
              </div>
              <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-white">
                Fayda ID Print Card Generator
              </h1>
              <p className="text-sm text-slate-400 leading-relaxed">
                Upload up to 5 Fayda ID PDFs. Our backend extracts citizen details, photos, and QR codes via Gemini AI, arranging them into standardized, print-ready card layouts.
              </p>
            </div>

            {/* Feature Highlights */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 max-w-4xl mx-auto">
              <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800/80 flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 flex items-center justify-center shrink-0">
                  <Layers className="w-4 h-4" />
                </div>
                <div>
                  <h4 className="text-xs font-semibold text-slate-200">1 to 5 Multi-Card Batch</h4>
                  <p className="text-[11px] text-slate-400">Process single or multiple cards per run</p>
                </div>
              </div>

              <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800/80 flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-violet-500/10 border border-violet-500/20 text-violet-400 flex items-center justify-center shrink-0">
                  <Cpu className="w-4 h-4" />
                </div>
                <div>
                  <h4 className="text-xs font-semibold text-slate-200">AI Data Extraction</h4>
                  <p className="text-[11px] text-slate-400">Gemini-powered text & barcode parsing</p>
                </div>
              </div>

              <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800/80 flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 flex items-center justify-center shrink-0">
                  <ShieldCheck className="w-4 h-4" />
                </div>
                <div>
                  <h4 className="text-xs font-semibold text-slate-200">Print-Ready Output</h4>
                  <p className="text-[11px] text-slate-400">Standard card sizing & high DPI layout</p>
                </div>
              </div>
            </div>

            {/* Main Uploader Box */}
            <div className="max-w-4xl mx-auto bg-slate-900/70 border border-slate-800 rounded-3xl p-6 sm:p-8 shadow-xl backdrop-blur-sm">
              <PdfSlotUploader
                files={files}
                setFiles={setFiles}
                onGenerate={handleGenerate}
                isLoading={isLoading}
              />
            </div>
          </div>
        )}
      </main>

      <footer className="border-t border-slate-800/80 py-6 text-center text-xs text-slate-500">
        AutoPress &copy; {new Date().getFullYear()} &bull; Digital Print Automation
      </footer>
    </div>
  );
}
