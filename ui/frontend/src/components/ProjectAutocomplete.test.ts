import { afterEach, describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";

import ProjectAutocomplete from "@/components/ProjectAutocomplete.vue";

import { stubFetch } from "@/testing/fixtures";

afterEach(() => {
  document.body.innerHTML = "";
});

describe("ProjectAutocomplete", () => {
  it("lists projects, filters by input, and selects with the keyboard", async () => {
    const { calls } = stubFetch((url) => {
      if (url.startsWith("/api/projects")) {
        return { projects: ["/Users/example/app", "/Users/example/lib"], revision: 1, refreshing: false };
      }
      return {};
    });

    const wrapper = mount(ProjectAutocomplete, {
      props: {
        modelValue: "",
        harness: "",
        archived: false,
      },
      attachTo: document.body,
    });

    await wrapper.find("input").trigger("focus");
    await new Promise((resolve) => setTimeout(resolve, 0));
    await wrapper.vm.$nextTick();

    expect(calls.some((url) => url.startsWith("/api/projects?"))).toBe(true);
    const options = wrapper.findAll(".project-option button");
    expect(options).toHaveLength(2);
    expect(wrapper.find("ul").isVisible()).toBe(true);

    const input = wrapper.find("input");
    (input.element as HTMLInputElement).value = "lib";
    await input.trigger("input");
    await wrapper.vm.$nextTick();
    const filtered = wrapper.findAll(".project-option button");
    expect(filtered).toHaveLength(1);
    expect(filtered[0].text()).toBe("/Users/example/lib");

    await input.trigger("keydown", { key: "ArrowDown" });
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".project-option.active button").text()).toBe("/Users/example/lib");

    await input.trigger("keydown", { key: "Enter" });
    await wrapper.vm.$nextTick();
    const emitted = wrapper.emitted("update:modelValue");
    expect(emitted?.[emitted!.length - 1]).toEqual(["/Users/example/lib"]);
    expect(wrapper.emitted("select")).toHaveLength(1);
    expect(wrapper.find("ul").isVisible()).toBe(false);
  });

  it("passes harness and archived filters to the projects API", async () => {
    const { calls } = stubFetch(() => ({ projects: [], revision: 1, refreshing: false }));
    const wrapper = mount(ProjectAutocomplete, {
      props: { modelValue: "", harness: "qoder-cn", archived: true },
      attachTo: document.body,
    });
    await wrapper.find("input").trigger("focus");
    await new Promise((resolve) => setTimeout(resolve, 0));
    const params = new URLSearchParams(calls[0].split("?")[1]);
    expect(params.get("harness")).toBe("qoder-cn");
    expect(params.get("archived")).toBe("true");
  });

  it("emits update:modelValue while typing so v-model feeds the search cwd", async () => {
    stubFetch(() => ({ projects: ["/Users/example/app", "/Users/example/lib"], revision: 1, refreshing: false }));
    const wrapper = mount(ProjectAutocomplete, {
      props: { modelValue: "", harness: "", archived: false },
      attachTo: document.body,
    });
    await wrapper.find("input").trigger("focus");
    await new Promise((resolve) => setTimeout(resolve, 0));
    await wrapper.vm.$nextTick();

    const input = wrapper.find("input");
    (input.element as HTMLInputElement).value = "lib";
    await input.trigger("input");
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("update:modelValue")).toEqual([["lib"]]);

    // Simulate the parent's v-model write-back: the filter term follows the
    // bound value, so the option list narrows without reopening.
    await wrapper.setProps({ modelValue: "lib" });
    await wrapper.vm.$nextTick();
    const options = wrapper.findAll(".project-option button");
    expect(options).toHaveLength(1);
    expect(options[0].text()).toBe("/Users/example/lib");
  });

  it("toggle button opens the dropdown and a second click closes it", async () => {
    stubFetch(() => ({ projects: ["/Users/example/app"], revision: 1, refreshing: false }));
    const wrapper = mount(ProjectAutocomplete, {
      props: { modelValue: "", harness: "", archived: false },
      attachTo: document.body,
    });
    const toggle = wrapper.find("button.project-toggle");
    const list = wrapper.find("ul");

    await toggle.trigger("click");
    await new Promise((resolve) => setTimeout(resolve, 0));
    await wrapper.vm.$nextTick();
    expect(list.isVisible()).toBe(true);
    expect(toggle.attributes("aria-expanded")).toBe("true");

    await toggle.trigger("click");
    await wrapper.vm.$nextTick();
    expect(list.isVisible()).toBe(false);
    expect(toggle.attributes("aria-expanded")).toBe("false");
  });

  it("tracks the active option with aria-activedescendant and clears it on close", async () => {
    stubFetch(() => ({ projects: ["/Users/example/app", "/Users/example/lib"], revision: 1, refreshing: false }));
    const wrapper = mount(ProjectAutocomplete, {
      props: { modelValue: "", harness: "", archived: false },
      attachTo: document.body,
    });
    const input = wrapper.find("input");
    await input.trigger("focus");
    await new Promise((resolve) => setTimeout(resolve, 0));
    await wrapper.vm.$nextTick();

    expect(input.attributes("aria-activedescendant")).toBeUndefined();

    await input.trigger("keydown", { key: "ArrowDown" });
    await wrapper.vm.$nextTick();
    expect(input.attributes("aria-activedescendant")).toBe("project-option-0");

    await input.trigger("keydown", { key: "ArrowDown" });
    await wrapper.vm.$nextTick();
    expect(input.attributes("aria-activedescendant")).toBe("project-option-1");

    await input.trigger("keydown", { key: "Escape" });
    await wrapper.vm.$nextTick();
    expect(input.attributes("aria-activedescendant")).toBeUndefined();
  });
});
