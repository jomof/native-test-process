// The Go side of the fixtures. Each program is a standalone `package main`
// file under fixtures/; the builder compiles them in named-files mode
// (`go build -o out fixtures/<prog>/<prog>.go`), so no package layout or
// external dependencies are needed.
module native-test-process-fixtures

go 1.21
