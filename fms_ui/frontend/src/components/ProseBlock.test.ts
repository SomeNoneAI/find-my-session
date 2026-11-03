import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";

import ProseBlock from "@/components/ProseBlock.vue";

const LONG_TEXT = "line\n".repeat(20); // 20 lines > 12: foldable

describe("ProseBlock", () => {
  it("starts collapsed for long text and expands on demand", async () => {
    const wrapper = mount(ProseBlock, { props: { text: LONG_TEXT } });
    expect(wrapper.classes()).toContain("foldable");
    expect(wrapper.classes()).not.toContain("expanded");

    await wrapper.find(".fold-button").trigger("click");
    expect(wrapper.classes()).toContain("expanded");
    expect(wrapper.classes()).not.toContain("foldable");
    expect(wrapper.find(".fold-button").text()).toBe("Show less");
  });

  it("resets the expanded state when the text changes", async () => {
    const wrapper = mount(ProseBlock, { props: { text: LONG_TEXT } });
    await wrapper.find(".fold-button").trigger("click");
    expect(wrapper.classes()).toContain("expanded");

    // A different prompt/summary reuses the component: it must render
    // collapsed again, like the old DOM-rebuilding implementation.
    await wrapper.setProps({ text: LONG_TEXT + "suffix" });
    await wrapper.vm.$nextTick();
    expect(wrapper.classes()).not.toContain("expanded");
    expect(wrapper.find(".fold-button").text()).toBe("Show more");
  });

  it("hides the fold button entirely for short text", async () => {
    const wrapper = mount(ProseBlock, { props: { text: "short text" } });
    expect(wrapper.find(".fold-button").exists()).toBe(false);
    expect(wrapper.classes()).not.toContain("foldable");
  });
});
