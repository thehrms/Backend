-> create your .env file
your .env file like
```
FIREBASE_PRIVATE_KEY_ID="fce522b367f90da57eea08964152387d896fce98"
FIREBASE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQCgrOBezKQ3lc9q\n/H1f9pcaohsugOWO0bTZt8uryfjw1OspKaxpYd/t98KznI4eiiE27gIu64Wgw4WN\nTlo+9p5byoEL0ihPn6SAvX4F0qPRLOiuUazg1+kQuo8GfpEQ4pO2/JEhQnb7RJ0M\nHcAe8U7Juy6akDGsOjbQtTJCCgsTuLB00EP+89M657jVMaaSIixalaCSrsaibZ6t\nfLQoJS6qAJlaAX/XVbsdMAflhPaWi02vHpPC6MofbavqLl9udxTYUI00dpIQKpgQ\n89hke5MP6U0vdopCypV39A4DPf1HO1HeXNuYHHiuSYadF/5EfBKUVJ4Bsw+vcno5\nb+hMFwp5AgMBAAECggEAE7oN5Q22dr2dpOrBgNvvYt12vV+lb4K3M8jRSHLobbcS\ndTAQ4zJZUifqX29v8nduiwYvPe/8LMf8mGP/h/3y5N2ouNkRSm9U/NpnA9N/+eFL\n4wUTltpjWsKw5zD4YgyTarK5Jc55ebGLn45yhUoGrJVe7CqacqUGEFtCw6FkiUPg\nfYqgOdLnBLNgWsfcZvXHJhbzh8eqkGsmgZEEt5lAuXwQsXggFdJyEeZZhViNcAIc\nkZSJQ85MwQFRzoQuhXmpOQvB7wby9E7W+jn1pw1amN5BP91/2zQ/a63kQNc127y0\nKxrBluVe+OTMPO2yY4a375w/kDfix/j4fClbPyj2tQKBgQDYGGtB9eepuUHzIKfq\nSL//lCUpRwDbYsj2rz17CZlg1M1Lip1HrlfSKM9hFH1e8uQGXwypVrZEc4X/D6lx\nvJjGaEsKwIkJ2IL93Mpl48NGbqN5qBOfrox6qc87S5gzAPUf2MyIhpdWeGstFiDN\noerUnXG+9rYCMVumsY5zOz3ZzQKBgQC+WI6ZVI0HuPJ8rKYT6e34ogG582xd7UnW\n9Gg1h0D0VKV2V7qlXtTi+Ftrn90RsRQICFA/kUTasLLsFdUs5HVEbswXFqORe82l\nMbCxeXEZIvWxm+6Ak89NIfQNHcdBGemlPeN4N4Bx6MD0l2ytNjDC02XBzAzLMT7P\n/rf+9MOXXQKBgHJ9LYZ65Ew1zM0lRhGIjcC5Gp8t8TRKuDKKUcZ4JXz6AfK98+pg\nYkMEQCstEedWRJ1jim/Fczf9BMdH4vxRcZfc9bUyoOhIf85ERi+JZpJQV+hCtnLp\npZ/vi83clTygiz5ePK8wr8mubwoqKSMJYENZT0Rfrbqnr+k3NUOz5WcZAoGBALXI\no18iFZIjeknBJNbt2RxTtGxfYsYNQTCtt/wvEMSHNoJf5FvcxlmBMOYHBbzIrcXC\nEsmytdxZVncLnsxB3xCc9AK01z+wycQTQZkszutfrN+TeOKIxzj1zTrdjpbI5Y+v\nHFeKQfwHeofdOafukgDunUbI1gsUG9XOgPBX15ftAoGBAILB6hWq5Sm19iOhrA0R\nxZTVYVNzghcluom1Eq2yGBxrColyHrF62+e0rybPQLt3v7lf3Wb1KZolYEVDLVxm\nb6Ig7A+gKY/tz5Tpfr83xn3bnPkCQXIbETLAMmDRpYjuLnIOHh+PEClYrKnjL1WE\n1HCzm3plIzi+apxpaAZ8zU4q\n-----END PRIVATE KEY-----"
FIREBASE_CLIENT_EMAIL="firebase-adminsdk-fbsvc@aihrms2.iam.gserviceaccount.com"
FIREBASE_CLIENT_ID="112319207679887151274"
FIREBASE_CLIENT_CERT_URL="https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-fbsvc%40aihrms2.iam.gserviceaccount.com"

FIREBASE_SERVICE_ACCOUNT_JSON="aihrms2-firebase-adminsdk-fbsvc-fce522b367.json"
OPENAI_API_KEY="sk-proj-USr92nxnW*******************"
# Flask Configuration
FLASK_ENV=development
FLASK_DEBUG=True

GEMINI_API_KEY=AIzaSyBt-***************

GEMINI_MODEL=models/gemini-2.0-flash-exp

# CORS Configuration
FRONTEND_URL=http://localhost:3000
```

Create Google Firebase configuration file inside the backend folder, and make sure the file is named:

```
aihrms2-firebase-adminsdk-fbsvc-fce522b367.json
```
and it's configurations

```
{
  "type": "service_account",
  "project_id": "aihrms2",
  "private_key_id": "fce522b367f90da57eea08964152387d896fce98",
  "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQCgrOBezKQ3lc9q\n/H1f9pcaohsugOWO0bTZt8uryfjw1OspKaxpYd/t98KznI4eiiE27gIu64Wgw4WN\nTlo+9p5byoEL0ihPn6SAvX4F0qPRLOiuUazg1+kQuo8GfpEQ4pO2/JEhQnb7RJ0M\nHcAe8U7Juy6akDGsOjbQtTJCCgsTuLB00EP+89M657jVMaaSIixalaCSrsaibZ6t\nfLQoJS6qAJlaAX/XVbsdMAflhPaWi02vHpPC6MofbavqLl9udxTYUI00dpIQKpgQ\n89hke5MP6U0vdopCypV39A4DPf1HO1HeXNuYHHiuSYadF/5EfBKUVJ4Bsw+vcno5\nb+hMFwp5AgMBAAECggEAE7oN5Q22dr2dpOrBgNvvYt12vV+lb4K3M8jRSHLobbcS\ndTAQ4zJZUifqX29v8nduiwYvPe/8LMf8mGP/h/3y5N2ouNkRSm9U/NpnA9N/+eFL\n4wUTltpjWsKw5zD4YgyTarK5Jc55ebGLn45yhUoGrJVe7CqacqUGEFtCw6FkiUPg\nfYqgOdLnBLNgWsfcZvXHJhbzh8eqkGsmgZEEt5lAuXwQsXggFdJyEeZZhViNcAIc\nkZSJQ85MwQFRzoQuhXmpOQvB7wby9E7W+jn1pw1amN5BP91/2zQ/a63kQNc127y0\nKxrBluVe+OTMPO2yY4a375w/kDfix/j4fClbPyj2tQKBgQDYGGtB9eepuUHzIKfq\nSL//lCUpRwDbYsj2rz17CZlg1M1Lip1HrlfSKM9hFH1e8uQGXwypVrZEc4X/D6lx\nvJjGaEsKwIkJ2IL93Mpl48NGbqN5qBOfrox6qc87S5gzAPUf2MyIhpdWeGstFiDN\noerUnXG+9rYCMVumsY5zOz3ZzQKBgQC+WI6ZVI0HuPJ8rKYT6e34ogG582xd7UnW\n9Gg1h0D0VKV2V7qlXtTi+Ftrn90RsRQICFA/kUTasLLsFdUs5HVEbswXFqORe82l\nMbCxeXEZIvWxm+6Ak89NIfQNHcdBGemlPeN4N4Bx6MD0l2ytNjDC02XBzAzLMT7P\n/rf+9MOXXQKBgHJ9LYZ65Ew1zM0lRhGIjcC5Gp8t8TRKuDKKUcZ4JXz6AfK98+pg\nYkMEQCstEedWRJ1jim/Fczf9BMdH4vxRcZfc9bUyoOhIf85ERi+JZpJQV+hCtnLp\npZ/vi83clTygiz5ePK8wr8mubwoqKSMJYENZT0Rfrbqnr+k3NUOz5WcZAoGBALXI\no18iFZIjeknBJNbt2RxTtGxfYsYNQTCtt/wvEMSHNoJf5FvcxlmBMOYHBbzIrcXC\nEsmytdxZVncLnsxB3xCc9AK01z+wycQTQZkszutfrN+TeOKIxzj1zTrdjpbI5Y+v\nHFeKQfwHeofdOafukgDunUbI1gsUG9XOgPBX15ftAoGBAILB6hWq5Sm19iOhrA0R\nxZTVYVNzghcluom1Eq2yGBxrColyHrF62+e0rybPQLt3v7lf3Wb1KZolYEVDLVxm\nb6Ig7A+gKY/tz5Tpfr83xn3bnPkCQXIbETLAMmDRpYjuLnIOHh+PEClYrKnjL1WE\n1HCzm3plIzi+apxpaAZ8zU4q\n-----END PRIVATE KEY-----\n",
  "client_email": "firebase-adminsdk-fbsvc@aihrms2.iam.gserviceaccount.com",
  "client_id": "112319207679887151274",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-fbsvc%40aihrms2.iam.gserviceaccount.com",
  "universe_domain": "googleapis.com"
}

```
