import React, { useRef, useState } from 'react';
import { UploadCloud, FileText, Trash2, Plus, AlertCircle, Sparkles } from 'lucide-react';

export default function PdfSlotUploader({ files, setFiles, onGenerate, isLoading }) {
  const [isDragOver, setIsDragOver] = useState(false);
  const [validationError, setValidationError] = useState('');
  const fileInputRef = useRef(null);

  const formatFileSize = (bytes) => {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
  };

  const handleAddFiles = (incomingFiles) => {
    setValidationError('');
    const newPdfs = Array.from(incomingFiles).filter(
      (f) => f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf')
    );

    if (newPdfs.length === 0) {
      setValidationError('Please select valid PDF file(s).');
      return;
    }

    if (files.length + newPdfs.length > 5) {
      setValidationError(`You can only upload up to 5 PDFs in total. (${files.length} already uploaded)`);
      return;
    }

    setFiles((prev) => [...prev, ...newPdfs]);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragOver(false);
    if (isLoading) return;
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleAddFiles(e.dataTransfer.files);
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleAddFiles(e.target.files);
      e.target.value = '';
    }
  };

  const removeFile = (index) => {
    if (isLoading) return;
    setFiles((prev) => prev.filter((_, i) => i !== index));
    setValidationError('');
  };

  const clearAll = () => {
    if (isLoading) return;
    setFiles([]);
    setValidationError('');
  };

  return (
    <div className="space-y-6">
      {/* Drop Zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          if (!isLoading && files.length < 5) setIsDragOver(true);
        }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={handleDrop}
        onClick={() => {
          if (!isLoading && files.length < 5 && fileInputRef.current) {
            fileInputRef.current.click();
          }
        }}
        className={`relative border-2 border-dashed rounded-2xl p-8 text-center transition-all cursor-pointer ${
          isDragOver
            ? 'border-indigo-500 bg-indigo-500/10 scale-[1.01]'
            : files.length >= 5
            ? 'border-slate-800 bg-slate-900/30 cursor-not-allowed opacity-75'
            : 'border-slate-700/80 hover:border-slate-500 bg-slate-900/40 hover:bg-slate-900/60'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,application/pdf"
          multiple
          onChange={handleFileChange}
          disabled={isLoading || files.length >= 5}
          className="hidden"
        />

        <div className="flex flex-col items-center justify-center gap-3">
          <div className="w-14 h-14 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 flex items-center justify-center">
            <UploadCloud className="w-7 h-7" />
          </div>
          <div>
            <h3 className="text-base font-semibold text-white">
              {files.length >= 5 ? 'Maximum 5 PDFs reached' : 'Upload Fayda ID PDF files'}
            </h3>
            <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
              Drag & drop up to 5 PDF files here, or click to browse. Each file will be mapped to a card slot.
            </p>
          </div>
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-slate-800/80 text-xs font-medium text-slate-300 border border-slate-700">
            <span>Slots used:</span>
            <span className="font-bold text-indigo-400">{files.length} / 5</span>
          </div>
        </div>
      </div>

      {validationError && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm">
          <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
          <span>{validationError}</span>
        </div>
      )}

      {/* Slots List (1 to 5) */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            Card Slots Allocation
          </h4>
          {files.length > 0 && (
            <button
              onClick={clearAll}
              disabled={isLoading}
              className="text-xs text-slate-400 hover:text-rose-400 transition-colors disabled:opacity-50"
            >
              Clear all
            </button>
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-5 gap-3">
          {[0, 1, 2, 3, 4].map((slotIndex) => {
            const file = files[slotIndex];
            const slotNumber = slotIndex + 1;

            if (file) {
              return (
                <div
                  key={slotIndex}
                  className="relative group p-3.5 rounded-xl bg-slate-900 border border-indigo-500/30 hover:border-indigo-500/60 transition-all flex flex-col justify-between shadow-sm"
                >
                  <div className="flex items-center justify-between gap-1 mb-2">
                    <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                      Slot {slotNumber}
                    </span>
                    <button
                      onClick={() => removeFile(slotIndex)}
                      disabled={isLoading}
                      title="Remove PDF"
                      className="p-1 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 transition-colors disabled:opacity-50"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <div className="flex items-start gap-2.5">
                    <FileText className="w-5 h-5 text-indigo-400 shrink-0 mt-0.5" />
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-medium text-slate-200 truncate" title={file.name}>
                        {file.name}
                      </p>
                      <p className="text-[10px] text-slate-400">{formatFileSize(file.size)}</p>
                    </div>
                  </div>
                </div>
              );
            }

            return (
              <div
                key={slotIndex}
                onClick={() => {
                  if (!isLoading && fileInputRef.current) fileInputRef.current.click();
                }}
                className="p-3.5 rounded-xl border border-dashed border-slate-800 hover:border-slate-700 bg-slate-950/40 hover:bg-slate-900/30 transition-all flex flex-col items-center justify-center text-center cursor-pointer min-h-[90px]"
              >
                <span className="text-[10px] font-semibold text-slate-500 mb-1">Slot {slotNumber}</span>
                <Plus className="w-4 h-4 text-slate-600 mb-1" />
                <span className="text-[10px] text-slate-500">Empty</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Action Button */}
      <div>
        <button
          onClick={onGenerate}
          disabled={isLoading || files.length === 0}
          className="w-full py-4 px-6 rounded-2xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white font-semibold text-sm shadow-xl shadow-indigo-600/25 transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
        >
          {isLoading ? (
            <>
              <span className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              <span>Processing {files.length} Card{files.length > 1 ? 's' : ''} & Generating Print PNG...</span>
            </>
          ) : (
            <>
              <Sparkles className="w-4 h-4" />
              <span>
                {files.length === 0
                  ? 'Select at least 1 PDF to Generate'
                  : `Generate Print PNG (${files.length} ID Card${files.length > 1 ? 's' : ''})`}
              </span>
            </>
          )}
        </button>
      </div>
    </div>
  );
}

