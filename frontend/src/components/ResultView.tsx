import { useState } from 'react';
import { motion } from 'framer-motion';
import {
  ArrowLeftIcon,
  ArrowDownTrayIcon,
  DocumentTextIcon,
  ShieldCheckIcon,
  ClockIcon
} from '@heroicons/react/24/outline';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { TaskInfo, MaskingReport, downloadMaskedFile } from '../services/api';

interface ResultViewProps {
  task: TaskInfo;
  report: MaskingReport | null;
  onBack: () => void;
  isLoading: boolean;
}

export default function ResultView({ task, report, onBack, isLoading }: ResultViewProps) {
  const [isDownloading, setIsDownloading] = useState(false);

  const handleDownloadFile = async () => {
    setIsDownloading(true);
    try {
      const blob = await downloadMaskedFile(task.task_id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `masked_${task.filename}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Download failed:', error);
    } finally {
      setIsDownloading(false);
    }
  };

  const handleDownloadReport = async () => {
    if (!report) return;
    
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `report_${task.task_id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const getRiskColor = (level: string) => {
    switch (level) {
      case 'LOW': return { bg: 'bg-green-500', text: 'text-green-700', light: 'bg-green-100' };
      case 'MEDIUM': return { bg: 'bg-yellow-500', text: 'text-yellow-700', light: 'bg-yellow-100' };
      case 'HIGH': return { bg: 'bg-red-500', text: 'text-red-700', light: 'bg-red-100' };
      default: return { bg: 'bg-gray-500', text: 'text-gray-700', light: 'bg-gray-100' };
    }
  };

  const getRiskLabel = (level: string) => {
    switch (level) {
      case 'LOW': return 'Low Risk';
      case 'MEDIUM': return 'Medium Risk';
      case 'HIGH': return 'High Risk';
      default: return 'Unknown';
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  };

  const chartColors = ['#30BA78', '#3B82F6', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899'];

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-suse-green"></div>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="space-y-6"
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <button
          onClick={onBack}
          className="flex items-center space-x-2 text-gray-600 hover:text-gray-900 transition-colors"
        >
          <ArrowLeftIcon className="w-5 h-5" />
          <span>Back</span>
        </button>
        
        <div className="flex items-center space-x-3">
          <motion.button
            onClick={handleDownloadFile}
            disabled={isDownloading}
            className="flex items-center space-x-2 px-4 py-2 bg-suse-green text-white rounded-lg hover:bg-suse-green/90 transition-colors shadow-lg shadow-suse-green/25"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            <ArrowDownTrayIcon className="w-5 h-5" />
            <span>{isDownloading ? 'Downloading...' : 'Download Masked File'}</span>
          </motion.button>
          
          <motion.button
            onClick={handleDownloadReport}
            className="flex items-center space-x-2 px-4 py-2 border-2 border-suse-green text-suse-green rounded-lg hover:bg-suse-green/10 transition-colors"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            <DocumentTextIcon className="w-5 h-5" />
            <span>Download Report</span>
          </motion.button>
        </div>
      </div>

      {/* File Info Card */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6">
        <div className="flex items-start justify-between">
          <div className="flex items-center space-x-4">
            <div className="p-3 bg-suse-green-50 rounded-xl">
              <DocumentTextIcon className="w-8 h-8 text-suse-green" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-gray-900">{task.filename}</h2>
              {report && (
                <div className="flex items-center space-x-4 mt-2 text-sm text-gray-500">
                  <span>{formatFileSize(report.file_info.size_bytes)}</span>
                  <span>•</span>
                  <span>{report.file_info.lines_total.toLocaleString()} 行</span>
                  <span>•</span>
                  <span className="flex items-center">
                    <ClockIcon className="w-4 h-4 mr-1" />
                    {(report.summary.processing_time_ms / 1000).toFixed(2)}s
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Risk Score */}
          {report && (
            <div className="text-right">
              <div className={`inline-flex items-center space-x-2 px-4 py-2 rounded-xl ${getRiskColor(report.summary.risk_level).light}`}>
                <ShieldCheckIcon className={`w-5 h-5 ${getRiskColor(report.summary.risk_level).text}`} />
                <span className={`font-bold ${getRiskColor(report.summary.risk_level).text}`}>
                  Risk Score: {report.summary.risk_score}/100
                </span>
              </div>
              <p className={`mt-2 text-sm font-medium ${getRiskColor(report.summary.risk_level).text}`}>
                {getRiskLabel(report.summary.risk_level)}
              </p>
            </div>
          )}
        </div>

        {/* Risk Progress Bar */}
        {report && (
          <div className="mt-6">
            <div className="h-3 bg-gray-200 rounded-full overflow-hidden">
              <motion.div
                className={`h-full rounded-full ${getRiskColor(report.summary.risk_level).bg}`}
                initial={{ width: 0 }}
                animate={{ width: `${report.summary.risk_score}%` }}
                transition={{ duration: 0.8, ease: 'easeOut' }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Statistics */}
      {report && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="bg-white rounded-xl shadow-sm border border-gray-200 p-5"
          >
            <p className="text-sm text-gray-500">Sensitive Data Detected</p>
            <p className="text-3xl font-bold text-gray-900 mt-1">
              {report.summary.total_matches.toLocaleString()}
            </p>
          </motion.div>
          
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="bg-white rounded-xl shadow-sm border border-gray-200 p-5"
          >
            <p className="text-sm text-gray-500">Rules Applied</p>
            <p className="text-3xl font-bold text-gray-900 mt-1">
              {report.breakdown.length}
            </p>
          </motion.div>
          
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="bg-white rounded-xl shadow-sm border border-gray-200 p-5"
          >
            <p className="text-sm text-gray-500">Whitelist Skipped</p>
            <p className="text-3xl font-bold text-gray-900 mt-1">
              {report.summary.whitelist_skipped}
            </p>
          </motion.div>
        </div>
      )}

      {/* Chart and Details */}
      {report && report.breakdown.length > 0 && (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Sensitive Data Distribution</h3>
          
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={report.breakdown.map(b => ({
                  name: b.rule_name_zh,
                  value: b.matches
                }))}
                layout="vertical"
                margin={{ top: 5, right: 30, left: 80, bottom: 5 }}
              >
                <XAxis type="number" />
                <YAxis type="category" dataKey="name" width={80} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#fff',
                    border: '1px solid #e5e7eb',
                    borderRadius: '8px',
                    boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)'
                  }}
                />
                <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                  {report.breakdown.map((_, index) => (
                    <Cell key={`cell-${index}`} fill={chartColors[index % chartColors.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Examples */}
      {report && report.breakdown.some(b => b.examples.length > 0) && (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Masking Examples</h3>
          
          <div className="space-y-4">
            {report.breakdown.filter(b => b.examples.length > 0).map((rule) => (
              <div key={rule.rule_id} className="border border-gray-200 rounded-xl overflow-hidden">
                <div className="bg-gray-50 px-4 py-2 border-b border-gray-200">
                  <span className="font-medium text-gray-700">{rule.rule_name_zh}</span>
                  <span className="ml-2 text-sm text-gray-500">({rule.matches} 处)</span>
                </div>
                
                <div className="divide-y divide-gray-100">
                  {rule.examples.map((example, index) => (
                    <div key={index} className="px-4 py-3 font-mono text-sm">
                      <div className="flex items-center space-x-2 mb-1">
                        <span className="text-gray-400 w-16">Line {example.line}</span>
                        <span className="diff-removed px-2 py-0.5 rounded">{example.original}</span>
                      </div>
                      <div className="flex items-center space-x-2">
                        <span className="text-gray-400 w-16"></span>
                        <span className="diff-added px-2 py-0.5 rounded">{example.masked}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </motion.div>
  );
}
