import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";

import PromptListing from "@/components/PromptListing.vue";
import type { PromptListingDTO, UserPromptDTO } from "@/types";

function prompt(index: number, text = `prompt ${index}`): UserPromptDTO {
  return { index, timestamp: "2026-10-20T09:00:05.000Z", text };
}

function listing(overrides: Partial<PromptListingDTO> = {}): PromptListingDTO {
  return {
    ref: "qoder-cn:aaaaaaaa",
    harness: "qoder-cn",
    session_id: "aaaaaaaa-0000-4000-8000-000000000000",
    path: "/store/aaaaaaaa.jsonl",
    cwd: "/Users/example/app",
    archived: false,
    total: 3,
    offset: 0,
    limit: 2,
    order: "oldest",
    returned: 2,
    has_more: true,
    prompts: [prompt(1), prompt(2)],
    ...overrides,
  };
}

describe("PromptListing", () => {
  it("pages forward only when more prompts exist", async () => {
    const wrapper = mount(PromptListing, {
      props: { listing: listing(), loading: false, error: "", order: "oldest" },
    });
    const buttons = wrapper.findAll(".page-button");
    expect(buttons[0].attributes("disabled")).toBeDefined();
    expect(buttons[1].attributes("disabled")).toBeUndefined();

    await buttons[1].trigger("click");
    expect(wrapper.emitted("page")).toEqual([[1]]);
  });

  it("changes order and resets through the toolbar select", async () => {
    const wrapper = mount(PromptListing, {
      props: { listing: listing(), loading: false, error: "", order: "oldest" },
    });
    await wrapper.find("select").setValue("newest");
    expect(wrapper.emitted("update:order")).toEqual([["newest"]]);
  });

  it("shows an empty-page note when the listing has prompts but none on this page", () => {
    const wrapper = mount(PromptListing, {
      props: {
        listing: listing({ prompts: [], returned: 0, has_more: false, offset: 2 }),
        loading: false,
        error: "",
        order: "oldest",
      },
    });
    expect(wrapper.find(".prompt-list").exists()).toBe(false);
    expect(wrapper.text().toLowerCase()).toContain("no user prompts");
  });
});
