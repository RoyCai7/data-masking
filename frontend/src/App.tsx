import { useState, useEffect, useCallback, useRef } from 'react';
import Header from './components/Header';
import FileUpload from './components/FileUpload';
import TaskList from './components/TaskList';
import ResultView from './components/ResultView';
import { TaskInfo, getTaskList, getTaskStatus, MaskingReport } from './services/api';

function App() {
  const [tasks, setTasks] = useState<TaskInfo[]>([]);
  const [selectedTask, setSelectedTask] = useState<TaskInfo | null>(null);
  const [selectedReport, setSelectedReport] = useState<MaskingReport | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const tasksRef = useRef(tasks);
  tasksRef.current = tasks;

  // Fetch tasks on mount
  const fetchTasks = useCallback(async () => {
    try {
      const data = await getTaskList();
      setTasks(data.tasks || []);
    } catch (error) {
      // Session might not exist yet, that's okay
      console.log('No tasks yet');
    }
  }, []);

  useEffect(() => {
    fetchTasks();
  }, [fetchTasks]);

  // Poll for task updates — single-flight setTimeout chain
  useEffect(() => {
    const hasPending = tasks.some(t => t.status === 'pending' || t.status === 'processing');
    if (!hasPending) return;

    let cancelled = false;
    const poll = async () => {
      if (cancelled) return;
      const current = tasksRef.current;
      try {
        const updatedTasks = await Promise.all(
          current.map(async (task) => {
            if (task.status === 'pending' || task.status === 'processing') {
              try {
                const updated = await getTaskStatus(task.task_id);
                return { ...task, ...updated };
              } catch {
                return task;
              }
            }
            return task;
          })
        );
        if (!cancelled) setTasks(updatedTasks);
      } catch {
        // ignore
      }
      if (!cancelled) {
        timerId = window.setTimeout(poll, 1500);
      }
    };

    let timerId = window.setTimeout(poll, 1500);
    return () => {
      cancelled = true;
      window.clearTimeout(timerId);
    };
  }, [tasks.some(t => t.status === 'pending' || t.status === 'processing')]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleUploadComplete = async () => {
    await fetchTasks();
  };

  const handleTaskSelect = async (task: TaskInfo) => {
    setSelectedTask(task);
    setIsLoading(true);
    
    try {
      const fullTask = await getTaskStatus(task.task_id);
      setSelectedTask({ ...task, ...fullTask });
      if (fullTask.report) {
        setSelectedReport(fullTask.report);
      }
    } catch (error) {
      console.error('Failed to fetch task details:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleBack = () => {
    setSelectedTask(null);
    setSelectedReport(null);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      
      {/* Disclaimer Banner */}
      <div className="bg-amber-50 border-b border-amber-200">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-start gap-3">
          <span className="text-amber-500 text-lg mt-0.5 shrink-0">⚠️</span>
          <p className="text-sm text-amber-800">
            <span className="font-semibold">Disclaimer: </span>
            This tool is intended to assist with data masking, but does not guarantee the complete removal of all sensitive information. Always perform a manual review of the masked output before sharing or publishing. Do not rely solely on this tool for data security compliance.
          </p>
        </div>
      </div>

      <main className="max-w-6xl mx-auto px-4 py-8">
        {selectedTask ? (
          <ResultView
            task={selectedTask}
            report={selectedReport}
            onBack={handleBack}
            isLoading={isLoading}
          />
        ) : (
          <div className="space-y-8">
            {/* Upload Section */}
            <section>
              <FileUpload onUploadComplete={handleUploadComplete} />
            </section>

            {/* Task List Section */}
            {tasks.length > 0 && (
              <section>
                <h2 className="text-lg font-semibold text-gray-900 mb-4">
                  My Processing History
                </h2>
                <TaskList
                  tasks={tasks}
                  onTaskSelect={handleTaskSelect}
                />
              </section>
            )}
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="mt-auto py-6 text-center text-sm text-gray-500">
        <p>© 2026 SUSE LLC. Data Masking Service v1.0</p>
        <p className="mt-1">Your data is only visible in this session and cannot be accessed by others</p>
      </footer>
    </div>
  );
}

export default App;
