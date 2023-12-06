// https://stackoverflow.com/questions/1349404/generate-random-string-characters-in-javascript
export function makeid(length: number) : string {
  let result = '';
  const characters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  const charactersLength = characters.length;
  let counter = 0;
  while (counter < length) {
    result += characters.charAt(Math.floor(Math.random() * charactersLength));
    counter += 1;
  }
  return result;
}

export async function hashid(message: string) : Promise<ArrayBuffer> {
  const encoder = new TextEncoder();
  const data = encoder.encode(message);
  const hash = await crypto.subtle.digest('SHA-256', data);
  return hash;
}

// https://stackoverflow.com/a/40031979/9014097
function buf2hex(buffer) { // buffer is an ArrayBuffer
  return Array.prototype.map.call(new Uint8Array(buffer), x => ('00' + x.toString(16)).slice(-2)).join('');
}

function getCookie(cookieName) {
  const cookies = document.cookie.split(';');

  for (let i = 0; i < cookies.length; i++) {
    const cookie = cookies[i].trim();
    if (cookie.startsWith(cookieName + '=')) return cookie.substring(cookieName.length + 1);
  }
  // Return null if the cookie is not found
  return null;
}

export async function setSessionID(page) {
  let id;
  if (page.data.session == null) {
    if (getCookie ("fallback_user_id") == null) {
      let rng = await hashid(makeid (24));
      document.cookie = `fallback_user_id=${buf2hex(rng)}`;
    }
    id = getCookie ("fallback_user_id");
  }
  else {
    id = await hashid(page.data?.session?.user.email);
    id = buf2hex(id);
  }
  document.cookie = `user_id=${id}`;
}