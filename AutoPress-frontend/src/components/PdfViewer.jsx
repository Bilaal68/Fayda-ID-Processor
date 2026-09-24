import React from 'react';
import { Download, ExternalLink, RotateCcw, CheckCircle2 } from 'lucide-react';

export default function PdfViewer({ blobUrl, filename, onReset }) {
  const handleDownload = () => {
    if (!blobUrl) return;
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = filename || 'fayda_id_cards.pdf';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  const handleOpenNewTab = () => {
    if (!blobUrl) return;
    window.open(blobUrl, '_blank');
  };

  return (
    <div className="flex flex-col h-full rounded-2xl bg-slate-900 border border-slate-800 overflow-hidden shadow-2xl">
      {/* Top Controls Bar */}
      <div className="px-6 py-4 border-b border-slate-800 bg-slate-900/80 backdrop-blur-md flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center justify-center">
            <CheckCircle2 className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-white leading-tight">Generated Print Ready PDF</h3>
            <p className="text-xs text-slate-400">{filename || 'fayda_id_cards.pdf'}</p>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={onReset}
            className="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-xs font-medium border border-slate-700/80 transition-colors flex items-center gap-1.5 cursor-pointer"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Process New Batch</span>
          </button>

          <button
            onClick={handleOpenNewTab}
            className="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-xs font-medium border border-slate-700/80 transition-colors flex items-center gap-1.5 cursor-pointer"
            title="Open in external tab"
          >
            <ExternalLink className="w-3.5 h-3.5" />
            <span>Open Tab</span>
          </button>

          <button
            onClick={handleDownload}
            className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-lg shadow-indigo-600/25 transition-all flex items-center gap-1.5 cursor-pointer"
          >
            <Download className="w-4 h-4" />
            <span>Download PDF</span>
          </button>
        </div>
      </div>

      {/* Embedded PDF Viewer */}
      <div className="relative flex-1 min-h-[600px] w-full bg-slate-950">
        <iframe
          src={`${blobUrl}#toolbar=1&navpanes=0`}
          title="Generated PDF Preview"
          className="w-full h-full border-none"
        />
      </div>
    </div>
  );
}

