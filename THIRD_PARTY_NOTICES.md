# Third-party notices

## FactorioMCP

- Upstream project: [sbarisic/FactorioMCP](https://github.com/sbarisic/FactorioMCP)
- Reviewed upstream revision: `f2fca61707efe3107e7a3738bb83d1505b0126f7`
- License: MIT
- Use: separately obtained backend; the patch in `backend-safety/backend-safety.patch` contains modifications to upstream files and context from those files. `backend-safety/SafetyTools.cs` and `backend-safety/AutoEngineerTools.cs` contain the added restricted tools. The combined patch also modifies upstream dispatch, startup and build configuration; the upstream notice below still applies to derived material.

The project's MIT license covers original AutoEngineer contributions. It does not replace upstream notices. Preserve the upstream license when copying or distributing the backend or material derived from it. The backend's license text is reproduced verbatim below, including its existing copyright placeholders; no upstream author, year, or license has been rewritten.

```text
MIT License

Copyright (c) [year] [fullname]

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Other dependencies and Factorio

Python, .NET, model runtimes, model weights, libraries and other separately installed components retain their own licenses. This project does not relicense or bundle them. Factorio and its assets belong to Wube Software and are not covered by this project's MIT license. This is an independent community project, not affiliated with or endorsed by Wube Software.
