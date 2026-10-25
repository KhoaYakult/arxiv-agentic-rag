// @vitest-environment jsdom
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Composer } from "@/components/composer";

function setup(pending = false, value = "Bài nói gì?") {
  const onSend = vi.fn();
  const onStop = vi.fn();
  const onChange = vi.fn();
  render(<Composer value={value} onChange={onChange} onSend={onSend} onStop={onStop} pending={pending} disabled={false} />);
  return { onSend, onStop, box: screen.getByRole("textbox") };
}

describe("Composer", () => {
  it("Enter sends, Shift+Enter does not", () => {
    const { onSend, box } = setup();
    fireEvent.keyDown(box, { key: "Enter", shiftKey: true });
    expect(onSend).not.toHaveBeenCalled();
    fireEvent.keyDown(box, { key: "Enter" });
    expect(onSend).toHaveBeenCalledTimes(1);
  });
  it("does not send while an IME composition is active (Vietnamese typing)", () => {
    const { onSend, box } = setup();
    fireEvent.keyDown(box, { key: "Enter", isComposing: true });
    fireEvent.keyDown(box, { key: "Enter", keyCode: 229 });
    expect(onSend).not.toHaveBeenCalled();
  });
  it("shows Stop while pending", () => {
    const { onStop } = setup(true);
    fireEvent.click(screen.getByRole("button", { name: "Dừng" }));
    expect(onStop).toHaveBeenCalled();
  });
  it("shows a message instead of silently dropping a too-short question", () => {
    const { onSend, box } = setup(false, "ab");
    fireEvent.keyDown(box, { key: "Enter" });
    expect(onSend).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("Câu hỏi quá ngắn.");
  });
});
