// Chuyen text chunk (markdown tho) thanh 1 dong chu thuong de HIEN THI trong trich dan.
// Chi dung de hien thi; KHONG dua vao findHighlight (no tu chuan hoa rieng).
export function plainQuote(text: string): string {
  return text
    .replace(/^\s*\|?[\s:-]*-{3,}[\s|:-]*$/gm, " ") // dong ngan cach bang: ---|---
    .replace(/^\s{0,3}#{1,6}\s+/gm, "") // dau # o dau dong
    .replace(/\*\*|__|`/g, "") // dam, gach chan kep, backtick (giu _ don: w_q, snake_case)
    .replace(/\|/g, " ") // dau | cua bang
    .replace(/\s+/g, " ")
    .trim();
}
