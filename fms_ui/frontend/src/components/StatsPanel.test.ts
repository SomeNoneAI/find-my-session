import { describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

import StatsPanel from "@/components/StatsPanel.vue";
import type { StatsResponseDTO } from "@/types";

function response(overrides: Partial<StatsResponseDTO["stats"][number]> = {}): StatsResponseDTO {
  return {
    stats: [
      {
        harness: "opencode",
        sessions: 48,
        sessions_with_usage: 48,
        tokens_input: 13810605,
        tokens_output: 560819,
        tokens_cache_read: 134351324,
        cost_usd: 34.777460454,
        ...overrides,
      },
      {
        harness: "kimi-code",
        sessions: 12,
        sessions_with_usage: 0,
        tokens_input: null,
        tokens_output: null,
        tokens_cache_read: null,
        cost_usd: null,
      },
    ],
  };
}

const fetchStats = vi.fn();

vi.mock("@/api", () => ({
  fetchStats: (signal?: AbortSignal) => fetchStats(signal),
}));

describe("StatsPanel", () => {
  it("renders per-harness rows with recorded totals", async () => {
    fetchStats.mockResolvedValue(response());
    const wrapper = mount(StatsPanel);
    await flushPromises();
    const text = wrapper.text();
    expect(text).toContain("opencode");
    expect(text).toContain("13,810,605");
    expect(text).toContain("34.7775");
  });

  it("marks harnesses without recorded usage", async () => {
    fetchStats.mockResolvedValue(response());
    const wrapper = mount(StatsPanel);
    await flushPromises();
    const kimiRow = wrapper.findAll("tbody tr")[1];
    expect(kimiRow.text()).toContain("-");
    expect(wrapper.text()).toContain("'");
  });

  it("shows the error state when loading fails", async () => {
    fetchStats.mockRejectedValue(new Error("boom"));
    const wrapper = mount(StatsPanel);
    await flushPromises();
    expect(wrapper.text()).toContain("boom");
  });

  it("emits close from the close button", async () => {
    fetchStats.mockResolvedValue(response());
    const wrapper = mount(StatsPanel);
    await flushPromises();
    await wrapper.find("button").trigger("click");
    expect(wrapper.emitted("close")).toHaveLength(1);
  });
});
