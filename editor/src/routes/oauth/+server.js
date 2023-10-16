import { redirect } from '@sveltejs/kit';
import { OAuth2Client } from 'google-auth-library';
import { session } from '@sveltejs/kit/node';

import {GOOGLE_ID,GOOGLE_SECRET} from '$env/static/private';

async function getUserData(access_token) {
  const response = await fetch(`https://www.googleapis.com/oauth2/v3/userinfo?access_token=${access_token}`);
  console.log('response',response);
  const data = await response.json();
  console.log('data',data);
}


export const GET = async ({ url}) => {
    const redirectURL = 'http://localhost:8000/oauth';

    const code = await url.searchParams.get('code');
    const state = await url.searchParams.get('state');

    console.log('returned state',state)
    console.log('returned code',code)

    try {
        const oAuth2Client = new OAuth2Client(
          GOOGLE_ID,
          GOOGLE_SECRET,
          redirectURL
        );
        const r = await oAuth2Client.getToken(code);
        // Make sure to set the credentials on the OAuth2 client.
        oAuth2Client.setCredentials(r.tokens);
        console.info('Tokens acquired.');
        const user = oAuth2Client.credentials;
        console.log('credentials',user);
        
        session.set({user});
        // const sessionObj = session.get(event?.locals);
        // sessionObj.user = {
        //   id: 123,
        //   username: 'exampleuser',
        // };
        // session.set(event?.locals, sessionObj);
      
        
        await getUserData(user.access_token);
      } catch (err) {
        console.log('Error logging in with OAuth2 user', err);
    }

    throw redirect(303, '/');
};