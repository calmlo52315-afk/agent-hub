import { create } from "zustand";
import type { ArtifactCard, CardType } from "@/types";

interface ArtifactStore {
  artifacts: ArtifactCard[];
  selectedArtifactId: string | null;
  activeTab: CardType | "all";
  loading: boolean;

  setArtifacts: (artifacts: ArtifactCard[]) => void;
  addArtifact: (artifact: ArtifactCard) => void;
  updateArtifact: (
    artifactId: string,
    updates: Partial<ArtifactCard>
  ) => void;
  setSelectedArtifactId: (id: string | null) => void;
  setActiveTab: (tab: CardType | "all") => void;
  setLoading: (v: boolean) => void;
  clearArtifacts: () => void;
  getByType: (type: CardType) => ArtifactCard[];
}

export const useArtifactStore = create<ArtifactStore>((set, get) => ({
  artifacts: [],
  selectedArtifactId: null,
  activeTab: "all",
  loading: false,

  setArtifacts: (artifacts) => set({ artifacts }),

  addArtifact: (artifact) =>
    set((state) => {
      const exists = state.artifacts.some(
        (a) => a.artifact_id === artifact.artifact_id
      );
      if (exists) {
        return {
          artifacts: state.artifacts.map((a) =>
            a.artifact_id === artifact.artifact_id ? artifact : a
          ),
        };
      }
      return { artifacts: [...state.artifacts, artifact] };
    }),

  updateArtifact: (artifactId, updates) =>
    set((state) => ({
      artifacts: state.artifacts.map((a) =>
        a.artifact_id === artifactId ? { ...a, ...updates } : a
      ),
    })),

  setSelectedArtifactId: (id) => set({ selectedArtifactId: id }),
  setActiveTab: (tab) => set({ activeTab: tab }),
  setLoading: (v) => set({ loading: v }),

  clearArtifacts: () =>
    set({ artifacts: [], selectedArtifactId: null }),

  getByType: (type) => get().artifacts.filter((a) => a.card_type === type),
}));

export { type ArtifactStore };
