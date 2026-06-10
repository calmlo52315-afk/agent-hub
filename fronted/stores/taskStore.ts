import { create } from "zustand";
import type { TaskSummary, TaskDetail, TaskStatus, AgentType } from "@/types";

interface TaskStore {
  tasks: TaskSummary[];
  currentTask: TaskDetail | null;
  loadingTasks: boolean;
  loadingDetail: boolean;

  setTasks: (tasks: TaskSummary[]) => void;
  addTask: (task: TaskSummary) => void;
  updateTask: (taskId: string, updates: Partial<TaskSummary>) => void;
  setCurrentTask: (task: TaskDetail | null) => void;
  setLoadingTasks: (v: boolean) => void;
  setLoadingDetail: (v: boolean) => void;
  clearTasks: () => void;
}

export const useTaskStore = create<TaskStore>((set) => ({
  tasks: [],
  currentTask: null,
  loadingTasks: false,
  loadingDetail: false,

  setTasks: (tasks) => set({ tasks }),

  addTask: (task) =>
    set((state) => {
      const exists = state.tasks.some((t) => t.task_id === task.task_id);
      if (exists) {
        return {
          tasks: state.tasks.map((t) =>
            t.task_id === task.task_id ? task : t
          ),
        };
      }
      return { tasks: [...state.tasks, task] };
    }),

  updateTask: (taskId, updates) =>
    set((state) => ({
      tasks: state.tasks.map((t) =>
        t.task_id === taskId ? { ...t, ...updates } : t
      ),
    })),

  setCurrentTask: (task) => set({ currentTask: task }),
  setLoadingTasks: (v) => set({ loadingTasks: v }),
  setLoadingDetail: (v) => set({ loadingDetail: v }),

  clearTasks: () => set({ tasks: [], currentTask: null }),
}));

export { type TaskStore };
