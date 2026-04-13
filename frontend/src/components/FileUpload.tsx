import { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { motion, AnimatePresence } from 'framer-motion';
import { CloudArrowUpIcon, DocumentTextIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { uploadFile } from '../services/api';

interface FileUploadProps {
  onUploadComplete: (taskId: string) => void;
}

export default function FileUpload({ onUploadComplete }: FileUploadProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [whitelist, setWhitelist] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onDrop = useCallback((acceptedFiles: File[]) => {
    if (acceptedFiles.length > 0) {
      setSelectedFile(acceptedFiles[0]);
      setError(null);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'text/plain': ['.txt', '.log', '.conf', '.cfg', '.ini'],
      'text/csv': ['.csv'],
      'application/json': ['.json'],
      'text/yaml': ['.yaml', '.yml'],
      'application/gzip': ['.tar.gz', '.tgz'],
      'application/x-bzip2': ['.tar.bz2', '.tbz2'],
      'application/x-xz': ['.tar.xz', '.txz'],
      'application/x-tar': ['.tar'],
      'application/zip': ['.zip'],
    },
    maxSize: 500 * 1024 * 1024, // 500MB
    multiple: false
  });

  const handleUpload = async () => {
    if (!selectedFile) return;

    setIsUploading(true);
    setError(null);

    try {
      const whitelistItems = whitelist.split(',').map(s => s.trim()).filter(Boolean);
      const result = await uploadFile(selectedFile, whitelistItems);
      onUploadComplete(result.task_id);
      setSelectedFile(null);
      setWhitelist('');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Upload failed, please try again');
    } finally {
      setIsUploading(false);
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    return (bytes / (1024 * 1024 * 1024)).toFixed(1) + ' GB';
  };

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">Upload File</h2>

      {/* Dropzone */}
      <div
        {...getRootProps()}
        className={`upload-zone relative border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all duration-300 ${
          isDragActive ? 'drag-active border-suse-green bg-suse-green-50' : 'border-gray-300 hover:border-suse-green'
        }`}
      >
        <input {...getInputProps()} />
        
        <motion.div
          className="upload-icon"
          animate={isDragActive ? { y: -8, scale: 1.1 } : { y: 0, scale: 1 }}
          transition={{ duration: 0.2 }}
        >
          <CloudArrowUpIcon className={`w-16 h-16 mx-auto mb-4 transition-colors ${
            isDragActive ? 'text-suse-green' : 'text-gray-400'
          }`} />
        </motion.div>

        <p className="text-lg font-medium text-gray-700">
          {isDragActive ? 'Drop to upload' : 'Drag & drop file here'}
        </p>
        <p className="mt-1 text-sm text-gray-500">
          or <span className="text-suse-green font-medium">click to browse</span>
        </p>
        <p className="mt-3 text-xs text-gray-400">
          Supports .txt .log .csv .json .yaml .conf .tar.gz .tgz .zip • Max 500MB
        </p>
      </div>

      {/* Selected File */}
      <AnimatePresence>
        {selectedFile && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="mt-4 p-4 bg-suse-green-50 rounded-xl border border-suse-green/20"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <DocumentTextIcon className="w-10 h-10 text-suse-green" />
                <div>
                  <p className="font-medium text-gray-900">{selectedFile.name}</p>
                  <p className="text-sm text-gray-500">{formatFileSize(selectedFile.size)}</p>
                </div>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setSelectedFile(null);
                }}
                className="p-1.5 rounded-full hover:bg-gray-200 transition-colors"
              >
                <XMarkIcon className="w-5 h-5 text-gray-500" />
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Whitelist Input */}
      <div className="mt-4">
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Whitelist (Optional)
        </label>
        <input
          type="text"
          value={whitelist}
          onChange={(e) => setWhitelist(e.target.value)}
          placeholder="Keywords to skip, comma-separated, e.g.: localhost, 127.0.0.1"
          className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-suse-green focus:border-suse-green outline-none transition-all text-sm"
        />
      </div>

      {/* Error Message */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm"
          >
            {error}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Upload Button */}
      <motion.button
        onClick={handleUpload}
        disabled={!selectedFile || isUploading}
        className={`mt-6 w-full py-3 px-6 rounded-xl font-semibold text-white transition-all ${
          selectedFile && !isUploading
            ? 'bg-suse-green hover:bg-suse-green/90 shadow-lg shadow-suse-green/25'
            : 'bg-gray-300 cursor-not-allowed'
        }`}
        whileHover={selectedFile && !isUploading ? { scale: 1.01 } : {}}
        whileTap={selectedFile && !isUploading ? { scale: 0.99 } : {}}
      >
        {isUploading ? (
          <span className="flex items-center justify-center">
            <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Processing...
          </span>
        ) : (
          'Start Masking'
        )}
      </motion.button>
    </div>
  );
}
