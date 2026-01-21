import { motion } from 'framer-motion';
import {
  DocumentTextIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
  ClockIcon,
  ArrowPathIcon
} from '@heroicons/react/24/outline';
import { TaskInfo } from '../services/api';

interface TaskListProps {
  tasks: TaskInfo[];
  onTaskSelect: (task: TaskInfo) => void;
}

export default function TaskList({ tasks, onTaskSelect }: TaskListProps) {
  const formatTime = (timestamp: number): string => {
    const now = Date.now() / 1000;
    const diff = now - timestamp;
    
    if (diff < 60) return 'just now';
    if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)} hr ago`;
    return new Date(timestamp * 1000).toLocaleDateString('en-US');
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircleIcon className="w-5 h-5 text-suse-green" />;
      case 'failed':
        return <ExclamationCircleIcon className="w-5 h-5 text-red-500" />;
      case 'processing':
        return <ArrowPathIcon className="w-5 h-5 text-blue-500 animate-spin" />;
      default:
        return <ClockIcon className="w-5 h-5 text-gray-400" />;
    }
  };

  const getStatusText = (status: string) => {
    switch (status) {
      case 'completed': return 'Completed';
      case 'failed': return 'Failed';
      case 'processing': return 'Processing';
      default: return 'Pending';
    }
  };

  const getRiskBadge = (riskLevel?: string) => {
    if (!riskLevel) return null;
    
    const colors = {
      LOW: 'bg-green-100 text-green-700',
      MEDIUM: 'bg-yellow-100 text-yellow-700',
      HIGH: 'bg-red-100 text-red-700'
    };
    
    const labels = {
      LOW: 'Low Risk',
      MEDIUM: 'Medium Risk',
      HIGH: 'High Risk'
    };
    
    return (
      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${colors[riskLevel as keyof typeof colors]}`}>
        {labels[riskLevel as keyof typeof labels]}
      </span>
    );
  };

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
      <div className="divide-y divide-gray-100">
        {tasks.map((task, index) => (
          <motion.div
            key={task.task_id}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.05 }}
            onClick={() => task.status === 'completed' && onTaskSelect(task)}
            className={`p-4 flex items-center justify-between transition-colors ${
              task.status === 'completed' ? 'hover:bg-gray-50 cursor-pointer' : ''
            }`}
          >
            <div className="flex items-center space-x-4">
              <div className="p-2 bg-gray-100 rounded-lg">
                <DocumentTextIcon className="w-6 h-6 text-gray-500" />
              </div>
              
              <div>
                <p className="font-medium text-gray-900">{task.filename}</p>
                <div className="flex items-center space-x-3 mt-1">
                  <span className="flex items-center space-x-1 text-sm text-gray-500">
                    {getStatusIcon(task.status)}
                    <span>{getStatusText(task.status)}</span>
                  </span>
                  
                  {task.status === 'processing' && (
                    <span className="text-sm text-blue-500">{task.progress}%</span>
                  )}
                  
                  {task.total_matches !== undefined && task.total_matches !== null && (
                    <span className="text-sm text-gray-500">
                      {task.total_matches} sensitive items
                    </span>
                  )}
                  
                  {getRiskBadge(task.risk_level)}
                </div>
              </div>
            </div>

            <div className="text-right">
              <p className="text-sm text-gray-500">{formatTime(task.created_at)}</p>
              
              {task.status === 'processing' && (
                <div className="mt-2 w-32 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                  <motion.div
                    className="h-full bg-suse-green rounded-full"
                    initial={{ width: 0 }}
                    animate={{ width: `${task.progress}%` }}
                    transition={{ duration: 0.3 }}
                  />
                </div>
              )}
              
              {task.status === 'completed' && (
                <p className="text-xs text-suse-green mt-1">Click to view details →</p>
              )}
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
